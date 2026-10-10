# Models

`registry.json` lists ONNX models the engine may load. No model is bundled: the
shipped perception is deterministic OpenCV. A registry entry is loaded only if
its file exists, its SHA-256 matches, its `output_format` is supported
(`xyxy_score_class_v1`: float `[N,6]` normalized `x1,y1,x2,y2,score,class`) and
`min_engine` is satisfied; otherwise it is refused with a reason
(`services/perception/tari_perception/registry.py`). Execution providers are
selected GPU-first (CUDA, DirectML, CoreML) with CPU fallback.

```json
{
  "registry_version": 1,
  "models": [
    {
      "name": "target-detector", "version": "0.1.0", "task": "target_detection",
      "file": "target-detector-0.1.0.onnx", "sha256": "<hex>",
      "input": { "width": 640, "height": 384 },
      "output_format": "xyxy_score_class_v1", "min_engine": "0.1.0", "classes": ["target"]
    }
  ]
}
```
