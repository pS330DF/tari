//! Windows.Graphics.Capture backend (Windows 10 1903+ / Windows 11).
//!
//! Frames arrive on a free-threaded frame pool, are copied to a CPU-readable
//! staging texture, converted (area-average downscale + center crop) and placed
//! in a one-slot mailbox. The streaming loop sends the newest packet, waits for
//! the engine's answer, and repeats; frames produced meanwhile replace each other
//! (latest-wins), so latency stays bounded and nothing queues.
//!
//! Status: compiles for x86_64-pc-windows-msvc; not yet run on Windows hardware.

use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use windows::core::{Interface, Result as WinResult, BOOL};
use windows::Foundation::TypedEventHandler;
use windows::Graphics::Capture::{Direct3D11CaptureFramePool, GraphicsCaptureItem};
use windows::Graphics::DirectX::Direct3D11::IDirect3DDevice;
use windows::Graphics::DirectX::DirectXPixelFormat;
use windows::Win32::Foundation::{HMODULE, HWND, LPARAM, RECT};
use windows::Win32::Graphics::Direct3D::D3D_DRIVER_TYPE_HARDWARE;
use windows::Win32::Graphics::Direct3D11::{
    D3D11CreateDevice, ID3D11Device, ID3D11DeviceContext, ID3D11Texture2D, D3D11_CPU_ACCESS_READ,
    D3D11_CREATE_DEVICE_BGRA_SUPPORT, D3D11_MAPPED_SUBRESOURCE, D3D11_MAP_READ, D3D11_SDK_VERSION, D3D11_TEXTURE2D_DESC,
    D3D11_USAGE_STAGING,
};
use windows::Win32::Graphics::Dxgi::IDXGIDevice;
use windows::Win32::Graphics::Gdi::{EnumDisplayMonitors, GetMonitorInfoW, HDC, HMONITOR, MONITORINFOEXW};
use windows::Win32::System::WinRT::Direct3D11::{CreateDirect3D11DeviceFromDXGIDevice, IDirect3DDxgiInterfaceAccess};
use windows::Win32::System::WinRT::Graphics::Capture::IGraphicsCaptureItemInterop;
use windows::Win32::System::WinRT::{RoInitialize, RO_INIT_MULTITHREADED};
use windows::Win32::UI::HiDpi::{SetProcessDpiAwarenessContext, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2};
use windows::Win32::UI::WindowsAndMessaging::{EnumWindows, GetWindowRect, GetWindowTextLengthW, GetWindowTextW, IsWindowVisible};

use crate::client::{BoxError, EngineClient, FrameOutcome};
use crate::image::Bgra;
use crate::epoch_ms;

pub enum Target {
    Window(isize),
    Monitor(usize),
}

/// Builds a FramePacket from a BGRA frame: (frame, session, frame_id, source_id, kind, label, acquired_ts).
pub type PacketBuilder = fn(&Bgra<'_>, &str, u64, &str, &str, &str, f64) -> Vec<u8>;

fn init_process() {
    unsafe {
        let _ = RoInitialize(RO_INIT_MULTITHREADED);
        let _ = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    }
}

fn window_title(hwnd: HWND) -> String {
    unsafe {
        let len = GetWindowTextLengthW(hwnd);
        if len <= 0 {
            return String::new();
        }
        let mut buf = vec![0u16; len as usize + 1];
        let n = GetWindowTextW(hwnd, &mut buf);
        String::from_utf16_lossy(&buf[..n as usize])
    }
}

unsafe extern "system" fn collect_window(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let out = &mut *(lparam.0 as *mut Vec<Value>);
    if IsWindowVisible(hwnd).as_bool() {
        let title = window_title(hwnd);
        let mut r = RECT::default();
        if !title.is_empty() && GetWindowRect(hwnd, &mut r).is_ok() && r.right > r.left && r.bottom > r.top {
            out.push(json!({ "hwnd": hwnd.0 as isize, "title": title, "width": r.right - r.left, "height": r.bottom - r.top }));
        }
    }
    BOOL(1)
}

unsafe extern "system" fn collect_monitor(hmon: HMONITOR, _hdc: HDC, _rect: *mut RECT, lparam: LPARAM) -> BOOL {
    let out = &mut *(lparam.0 as *mut Vec<HMONITOR>);
    out.push(hmon);
    BOOL(1)
}

fn monitors() -> Vec<HMONITOR> {
    let mut list: Vec<HMONITOR> = Vec::new();
    unsafe {
        let _ = EnumDisplayMonitors(None, None, Some(collect_monitor), LPARAM(&mut list as *mut _ as isize));
    }
    list
}

/// Capturable windows and monitors, as JSON.
pub fn list_targets() -> Result<Value, BoxError> {
    init_process();
    let mut windows: Vec<Value> = Vec::new();
    unsafe {
        EnumWindows(Some(collect_window), LPARAM(&mut windows as *mut _ as isize))?;
    }
    let mons: Vec<Value> = monitors()
        .into_iter()
        .enumerate()
        .map(|(i, h)| {
            let mut info = MONITORINFOEXW::default();
            info.monitorInfo.cbSize = std::mem::size_of::<MONITORINFOEXW>() as u32;
            let ok = unsafe { GetMonitorInfoW(h, &mut info as *mut MONITORINFOEXW as *mut _).as_bool() };
            let r = info.monitorInfo.rcMonitor;
            json!({ "index": i, "ok": ok, "width": r.right - r.left, "height": r.bottom - r.top })
        })
        .collect();
    Ok(json!({ "windows": windows, "monitors": mons }))
}

struct D3D {
    device: ID3D11Device,
    context: ID3D11DeviceContext,
    staging: Option<(ID3D11Texture2D, u32, u32)>,
}

// The D3D objects are only used while holding the mutex that wraps this struct.
unsafe impl Send for D3D {}

fn create_device() -> WinResult<(ID3D11Device, ID3D11DeviceContext, IDirect3DDevice)> {
    let mut device: Option<ID3D11Device> = None;
    let mut context: Option<ID3D11DeviceContext> = None;
    unsafe {
        D3D11CreateDevice(
            None,
            D3D_DRIVER_TYPE_HARDWARE,
            HMODULE::default(),
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            None,
            D3D11_SDK_VERSION,
            Some(&mut device),
            None,
            Some(&mut context),
        )?;
    }
    let device = device.expect("D3D11CreateDevice returned no device");
    let context = context.expect("D3D11CreateDevice returned no context");
    let dxgi: IDXGIDevice = device.cast()?;
    let inspectable = unsafe { CreateDirect3D11DeviceFromDXGIDevice(&dxgi)? };
    let winrt_device: IDirect3DDevice = inspectable.cast()?;
    Ok((device, context, winrt_device))
}

fn capture_item(target: &Target) -> Result<(GraphicsCaptureItem, String, String), BoxError> {
    let interop = windows::core::factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>()?;
    match *target {
        Target::Window(h) => {
            let hwnd = HWND(h as *mut core::ffi::c_void);
            let item: GraphicsCaptureItem = unsafe { interop.CreateForWindow(hwnd)? };
            Ok((item, format!("window:{h}"), window_title(hwnd)))
        }
        Target::Monitor(i) => {
            let mons = monitors();
            let hmon = *mons.get(i).ok_or("monitor index out of range")?;
            let item: GraphicsCaptureItem = unsafe { interop.CreateForMonitor(hmon)? };
            Ok((item, format!("monitor:{i}"), format!("Display {}", i + 1)))
        }
    }
}

/// Copy the frame texture to a staging texture and read it as BGRA.
fn read_frame(d3d: &mut D3D, texture: &ID3D11Texture2D) -> WinResult<(Vec<u8>, u32, u32, usize)> {
    let mut desc = D3D11_TEXTURE2D_DESC::default();
    unsafe { texture.GetDesc(&mut desc) };
    let (w, h) = (desc.Width, desc.Height);
    let need_new = !matches!(&d3d.staging, Some((_, sw, sh)) if *sw == w && *sh == h);
    if need_new {
        let mut sd = desc;
        sd.Usage = D3D11_USAGE_STAGING;
        sd.BindFlags = 0;
        sd.CPUAccessFlags = D3D11_CPU_ACCESS_READ.0 as u32;
        sd.MiscFlags = 0;
        sd.MipLevels = 1;
        sd.ArraySize = 1;
        let mut staging: Option<ID3D11Texture2D> = None;
        unsafe { d3d.device.CreateTexture2D(&sd, None, Some(&mut staging))? };
        d3d.staging = Some((staging.expect("staging texture"), w, h));
    }
    let staging = d3d.staging.as_ref().map(|(t, _, _)| t.clone()).expect("staging texture");
    unsafe {
        d3d.context.CopyResource(&staging, texture);
        let mut mapped = D3D11_MAPPED_SUBRESOURCE::default();
        d3d.context.Map(&staging, 0, D3D11_MAP_READ, 0, Some(&mut mapped))?;
        let stride = mapped.RowPitch as usize;
        let bytes = std::slice::from_raw_parts(mapped.pData as *const u8, stride * h as usize).to_vec();
        d3d.context.Unmap(&staging, 0);
        Ok((bytes, w, h, stride))
    }
}

struct Mailbox {
    slot: Mutex<Option<(Vec<u8>, u64)>>,
    ready: Condvar,
    superseded: Mutex<u64>,
}

/// Stream a window or monitor to the engine until `seconds` elapse (or forever).
pub fn stream(url: &str, target: Target, fps: f64, seconds: Option<f64>, build: PacketBuilder) -> Result<Value, BoxError> {
    init_process();
    if !GraphicsCaptureSession_is_supported() {
        return Err("Windows.Graphics.Capture is not supported on this system".into());
    }
    let (item, source_id, label) = capture_item(&target)?;
    let mut client = EngineClient::connect(url)?;
    let session = client.start_session(&source_id, "native_wgc", &label)?;
    let (device, context, winrt_device) = create_device()?;
    let d3d = Arc::new(Mutex::new(D3D { device, context, staging: None }));
    let mailbox = Arc::new(Mailbox { slot: Mutex::new(None), ready: Condvar::new(), superseded: Mutex::new(0) });
    let size = item.Size()?;
    let pool = Direct3D11CaptureFramePool::CreateFreeThreaded(&winrt_device, DirectXPixelFormat::B8G8R8A8UIntNormalized, 2, size)?;
    let capture = pool.CreateCaptureSession(&item)?;
    let _ = capture.SetIsCursorCaptureEnabled(false);
    let _ = capture.SetIsBorderRequired(false); // Windows 11; ignored where unsupported

    let interval = Duration::from_secs_f64(1.0 / fps.max(1.0));
    let last = Arc::new(Mutex::new(Instant::now() - interval));
    let frame_counter = Arc::new(Mutex::new(0u64));
    {
        let (d3d, mailbox, last, counter, session, source_id, label) =
            (d3d.clone(), mailbox.clone(), last.clone(), frame_counter.clone(), session.clone(), source_id.clone(), label.clone());
        pool.FrameArrived(&TypedEventHandler::<Direct3D11CaptureFramePool, windows::core::IInspectable>::new(move |sender, _| {
            let Some(pool) = sender.as_ref() else { return Ok(()) };
            let frame = pool.TryGetNextFrame()?;
            {
                let mut l = last.lock().unwrap();
                if l.elapsed() < interval {
                    return Ok(()); // rate cap: skip conversion entirely
                }
                *l = Instant::now();
            }
            let acquired = epoch_ms();
            let access: IDirect3DDxgiInterfaceAccess = frame.Surface()?.cast()?;
            let texture: ID3D11Texture2D = unsafe { access.GetInterface()? };
            let (bytes, w, h, stride) = read_frame(&mut d3d.lock().unwrap(), &texture)?;
            let id = {
                let mut c = counter.lock().unwrap();
                *c += 1;
                *c
            };
            let img = Bgra { data: &bytes, width: w, height: h, stride };
            let packet = build(&img, &session, id, &source_id, "native_wgc", &label, acquired);
            let mut slot = mailbox.slot.lock().unwrap();
            if slot.replace((packet, id)).is_some() {
                *mailbox.superseded.lock().unwrap() += 1; // newer frame replaced an unsent one
            }
            mailbox.ready.notify_one();
            Ok(())
        }))?;
    }
    capture.StartCapture()?;

    let started = Instant::now();
    let (mut results, mut dropped) = (0u64, 0u64);
    let mut rtts: Vec<f64> = Vec::new();
    loop {
        if let Some(limit) = seconds {
            if started.elapsed().as_secs_f64() >= limit {
                break;
            }
        }
        let next = {
            let guard = mailbox.slot.lock().unwrap();
            let (mut guard, _) = mailbox.ready.wait_timeout_while(guard, Duration::from_millis(500), |s| s.is_none()).unwrap();
            guard.take()
        };
        let Some((packet, id)) = next else { continue };
        let t0 = Instant::now();
        client.send_frame(packet)?;
        match client.wait_outcome(id)? {
            FrameOutcome::Result { .. } => {
                results += 1;
                rtts.push(t0.elapsed().as_secs_f64() * 1000.0);
            }
            FrameOutcome::Dropped { .. } => dropped += 1,
        }
    }
    capture.Close()?;
    pool.Close()?;
    let summary = client.end_session()?;
    rtts.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let pct = |q: f64| rtts.get(((rtts.len().max(1) - 1) as f64 * q).round() as usize).copied();
    Ok(json!({
        "ok": true, "session_id": session, "source": source_id, "results": results, "engine_dropped": dropped,
        "superseded_at_source": *mailbox.superseded.lock().unwrap(),
        "rtt_ms": { "p50": pct(0.5), "p95": pct(0.95) }, "engine_summary": summary,
    }))
}

#[allow(non_snake_case)]
fn GraphicsCaptureSession_is_supported() -> bool {
    windows::Graphics::Capture::GraphicsCaptureSession::IsSupported().unwrap_or(false)
}
