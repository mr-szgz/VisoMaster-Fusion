# ByteTrack downstream models and algorithms

Models and core algorithms used by the downstream stages of the standard video/webcam path, listed in execution order. Stages include direct landmark consumers and indirect consumers of the resulting aligned face crops and masks. Optional stages run only when enabled. Model options are alternatives, not a list of models that all run together.

1. **Recognition / identity filtering**
   - Models: **Inswapper128ArcFace, SimSwapArcFace, GhostArcFace, CSCSArcFace**.

2. **Dense landmark refinement → landmark smoothing**
   - Models: **FaceLandmark5, FaceLandmark68, FaceLandmark3d68, FaceLandmark98, FaceLandmark106, FaceLandmark203, FaceLandmark478, TUFA98, TUFA314, ORFormer98, HRFFA**.
   - HRFFA dependency: **DEIMv2Wholebody49Head**.
   - Smoothing: **motion-adaptive exponential moving average (EMA)**.

3. **Worker recognition → target matching → landmark adjustments**
   - Models: the same **four ArcFace options** as step 1.
   - Landmark adjustments: no additional model or specialized algorithm.

4. **Face alignment / cropping → pre-swap shaping → swapping**
   - Alignment templates: **ArcFace128, pose-aware ArcFace, FFHQ**, selected by swapper.
   - Shaping: **custom landmark-driven 2D mesh deformation**.
   - Primary swapper models: **Inswapper128, AlphaFace, InStyleSwapper256 A/B/C, DeepFaceLive DFM, SimSwap512, GhostFace v1/v2/v3, CSCS**.
   - Secondary swapper options: **Inswapper128, AlphaFace, InStyleSwapper256 A/B/C**.

5. **Profile-angle masks / segmentation safeguard angles**
   - Optional model input: **YawNet**, calculated earlier in the worker.
   - Otherwise: landmark-derived angles; no additional model or specialized algorithm.

6. **Beginning expression restoration → face editor → face shaping**
   - Expression, Simple/Advanced: **LivePortrait**.
   - Expression, Recast: **PerformRecast**.
   - Face editor: **LivePortrait**.
   - LivePortrait components: **Motion Extractor, Appearance Feature Extractor, Eye/Lip Retargeting, Stitching, Warping/SPADE**.
   - PerformRecast components: **Appearance Feature Extractor, Motion Extractor, Warping Module, SPADE Generator**.
   - Shaping: **custom landmark-driven 2D mesh deformation**.

7. **First face restorer**
   - Models: **GFPGAN-v1.4, GFPGAN-1024, CodeFormer, GPEN-256/512/1024/2048, RestoreFormer++, VQFR-v2, OSDFace**.

8. **Occluder → parser/mouth regions → CLIP mask → Restore Mouth/Eyes → XSeg**
   - Occlusion: **Occluder** (`occluder.onnx`).
   - Face/mouth parsing: **FaceParser ResNet34**.
   - Text masking: **CLIPSeg**, **ViT-B/16**, `rd64-uni-refined` weights.
   - Restore Mouth/Eyes: no additional model or specialized algorithm.
   - XSeg: **DFL XSeg**.
   - XSeg Mouth: **DFL XSeg output + FaceParser mouth/lip regions**; no separate mouth model.

9. **First-restorer automatic blending → after-first expression/editor/shaping**
   - Automatic restoration: **combined Variance-of-Laplacian and Thresholded Tenengrad sharpness scoring**.
   - Expression/editor: **LivePortrait or PerformRecast**, as in step 6.
   - Shaping: **custom landmark-driven 2D mesh deformation**.

10. **Second face restorer — regular position**
    - Models: the same **restorer options listed in step 7**, independently selected.

11. **After-second expression/editor/shaping**
    - Expression/editor: **LivePortrait or PerformRecast**, as in step 6.
    - Shaping: **custom landmark-driven 2D mesh deformation**.

12. **Auto Color → texture transfer → differencing → editor/shaping → color corrections**
    - Auto Color options: **CDF Histogram, CDF Histogram (Masked), Reinhard Transfer, Reinhard Transfer (Masked), AdaIN (Core Masked)**.
    - Auto Color reference stabilization: **EMA of color statistics**.
    - Texture extraction: **Gabor filter bank**.
    - Optional perceptual masks/differencing: **VGG feature model**, `combo_relu3_3_relu3_1`.
    - Editor: **LivePortrait**.
    - Shaping: **custom landmark-driven 2D mesh deformation**.
    - Manual color corrections: no additional model or specialized algorithm.

13. **Second face restorer — end position**
    - Models: the same **restorer options listed in step 7**.

14. **Post-restorer mouth enhancement → ending parser → ending color transfer → final mask processing**
    - Mouth-region parsing: **FaceParser ResNet34**.
    - Mouth obstacle masking, when enabled: **Occluder / DFL XSeg**.
    - Ending parser: **FaceParser ResNet34**.
    - Ending color options: **CDF Histogram, CDF Histogram (Masked), Reinhard Transfer, Reinhard Transfer (Masked), AdaIN (Core Masked)**.
    - Hair matting: **MODNet**.

15. **Face/mask placement back into the frame**
    - No additional model or specialized algorithm.

16. **Makeup**
    - Model: **FaceParser ResNet34**.

17. **Landmark overlays → cropped-face comparison previews**
    - No additional model or specialized algorithm.
