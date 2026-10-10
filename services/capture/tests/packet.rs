use std::path::PathBuf;

use tari_capture::{analysis_size, center_rect, crop_bgra_to_rgba, decode_frame_packet, downscale_bgra_to_rgba, encode_frame_packet, Bgra, PixelRect, RegionData};

fn pixels(w: u32, h: u32, seed: u32) -> Vec<u8> {
    (0..w * h).flat_map(|i| [((i + seed) % 256) as u8, ((i * 3 + seed) % 256) as u8, ((i * 7 + seed) % 256) as u8, 255]).collect()
}

#[test]
fn matches_python_and_typescript_golden_fixture() {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../packages/event-schema/fixtures/frame_packet_v1.bin");
    let golden = std::fs::read(fixture).expect("run `pnpm gen:fixtures`");
    let (gh, gp) = decode_frame_packet(&golden).unwrap();
    let (full, center) = (pixels(4, 2, 0), pixels(2, 2, 100));
    let ours = encode_frame_packet(
        "fixture-session", 42, "screen:0:0", "screen", "Fixture", 1700000000000.25, 1700000000003.5, (8, 4), true,
        &[
            RegionData { name: "full", src_rect: PixelRect { x: 0, y: 0, w: 8, h: 4 }, width: 4, height: 2, rgba: &full },
            RegionData { name: "center", src_rect: PixelRect { x: 3, y: 1, w: 2, h: 2 }, width: 2, height: 2, rgba: &center },
        ],
    )
    .unwrap();
    let (oh, op) = decode_frame_packet(&ours).unwrap();
    assert_eq!(oh, gh);
    assert_eq!(op, gp);
}

#[test]
fn rejects_wrong_region_size() {
    let data = vec![0u8; 15];
    let err = encode_frame_packet("s", 1, "x", "screen", "", 0.0, 0.0, (4, 4), false,
        &[RegionData { name: "full", src_rect: PixelRect { x: 0, y: 0, w: 4, h: 4 }, width: 2, height: 2, rgba: &data }]);
    assert!(err.is_err());
}

#[test]
fn geometry_matches_desktop_and_python() {
    assert_eq!(analysis_size(1920, 1080, 540, 1280), (960, 540));
    assert_eq!(analysis_size(2560, 1080, 540, 1280), (1280, 540));
    assert_eq!(analysis_size(3440, 1440, 540, 1280), (1280, 536));
    assert_eq!(analysis_size(800, 450, 540, 1280), (800, 450));
    let c = center_rect(1920, 1080, 384);
    assert_eq!((c.x, c.y, c.w, c.h), (768, 348, 384, 384));
}

#[test]
fn downscale_averages_and_swizzles() {
    // 4x2 BGRA: left half pure blue (B=255), right half pure red (R=255)
    let mut data = vec![0u8; 4 * 2 * 4];
    for y in 0..2 {
        for x in 0..4 {
            let o = (y * 4 + x) * 4;
            if x < 2 { data[o] = 255 } else { data[o + 2] = 255 }
            data[o + 3] = 255;
        }
    }
    let img = Bgra { data: &data, width: 4, height: 2, stride: 16 };
    let out = downscale_bgra_to_rgba(&img, 2, 1);
    assert_eq!(&out[0..4], &[0, 0, 255, 255]); // RGBA blue
    assert_eq!(&out[4..8], &[255, 0, 0, 255]); // RGBA red
    let crop = crop_bgra_to_rgba(&img, tari_capture::Rect { x: 1, y: 0, w: 2, h: 1 });
    assert_eq!(crop, vec![0, 0, 255, 255, 255, 0, 0, 255]);
}

#[test]
fn honors_row_stride_padding() {
    // 2x2 image with 4 bytes of padding per row (as D3D11 mapped textures have)
    let data = [10, 20, 30, 255, 40, 50, 60, 255, 0, 0, 0, 0, 70, 80, 90, 255, 100, 110, 120, 255, 0, 0, 0, 0];
    let img = Bgra { data: &data, width: 2, height: 2, stride: 12 };
    let crop = crop_bgra_to_rgba(&img, tari_capture::Rect { x: 0, y: 1, w: 2, h: 1 });
    assert_eq!(crop, vec![90, 80, 70, 255, 120, 110, 100, 255]);
}
