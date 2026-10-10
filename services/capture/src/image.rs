//! Pixel conversion: area-average downscale and crop of BGRA frames into RGBA
//! regions, with the same geometry rules as the desktop capture worker.

/// A borrowed BGRA8 image (e.g. a mapped D3D11 staging texture). `stride` is in bytes.
pub struct Bgra<'a> {
    pub data: &'a [u8],
    pub width: u32,
    pub height: u32,
    pub stride: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}

/// Analysis ("full" region) size: fixed height, capped width, never upscaled.
/// Mirrors `analysisSize` (TypeScript) and `analysis_size` (Python).
pub fn analysis_size(w: u32, h: u32, target_height: u32, max_width: u32) -> (u32, u32) {
    let scale = 1.0f64.min(target_height as f64 / h as f64).min(max_width as f64 / w as f64);
    (((w as f64 * scale).round() as u32).max(1), ((h as f64 * scale).round() as u32).max(1))
}

/// Unscaled center crop with an even-aligned origin (as in the desktop worker).
pub fn center_rect(w: u32, h: u32, size: u32) -> Rect {
    let cs = size.min(w).min(h);
    Rect { x: ((w - cs) / 2) & !1, y: ((h - cs) / 2) & !1, w: cs, h: cs }
}

/// Area-average downscale (box filter over each output pixel's source footprint), BGRA -> RGBA.
pub fn downscale_bgra_to_rgba(src: &Bgra<'_>, dst_w: u32, dst_h: u32) -> Vec<u8> {
    let (sw, sh) = (src.width as usize, src.height as usize);
    let (dw, dh) = (dst_w as usize, dst_h as usize);
    let mut out = vec![0u8; dw * dh * 4];
    let xr: Vec<(usize, usize)> = (0..dw)
        .map(|x| {
            let a = x * sw / dw;
            let b = ((x + 1) * sw / dw).max(a + 1).min(sw);
            (a, b)
        })
        .collect();
    for y in 0..dh {
        let y0 = y * sh / dh;
        let y1 = ((y + 1) * sh / dh).max(y0 + 1).min(sh);
        for (x, &(x0, x1)) in xr.iter().enumerate() {
            let (mut b, mut g, mut r, mut a) = (0u32, 0u32, 0u32, 0u32);
            for sy in y0..y1 {
                let row = &src.data[sy * src.stride..];
                for sx in x0..x1 {
                    let p = &row[sx * 4..sx * 4 + 4];
                    b += p[0] as u32;
                    g += p[1] as u32;
                    r += p[2] as u32;
                    a += p[3] as u32;
                }
            }
            let n = ((y1 - y0) * (x1 - x0)) as u32;
            let o = (y * dw + x) * 4;
            out[o] = ((r + n / 2) / n) as u8;
            out[o + 1] = ((g + n / 2) / n) as u8;
            out[o + 2] = ((b + n / 2) / n) as u8;
            out[o + 3] = ((a + n / 2) / n) as u8;
        }
    }
    out
}

/// Copy a rectangle of a BGRA image into a tightly packed RGBA buffer.
pub fn crop_bgra_to_rgba(src: &Bgra<'_>, rect: Rect) -> Vec<u8> {
    let mut out = vec![0u8; rect.w as usize * rect.h as usize * 4];
    for y in 0..rect.h as usize {
        let row = &src.data[(rect.y as usize + y) * src.stride + rect.x as usize * 4..];
        let o = y * rect.w as usize * 4;
        for x in 0..rect.w as usize {
            let p = &row[x * 4..x * 4 + 4];
            out[o + x * 4] = p[2];
            out[o + x * 4 + 1] = p[1];
            out[o + x * 4 + 2] = p[0];
            out[o + x * 4 + 3] = p[3];
        }
    }
    out
}
