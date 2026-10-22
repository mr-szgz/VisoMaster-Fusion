# Frame processing pipeline: models, configuration, and code references

Configuration links point to UI definitions; Parameter Usage links point to runtime code. Sizes are measured from downloaded model files in MiB, excluding TensorRT engines and download archives. Filenames are relative to `model_assets/`, except the CLIP backbone.

Step numbers retain the previously traced 17-step execution list. Reused models list their applicable locations. Source-preparation rows are not per-frame inference stages. Model choices are alternatives, not models that necessarily all run together. File sizes and source line references were inspected on 2026-10-22.

Shared enable/position controls:

- **Landmarks:** [LandmarkDetectToggle][land-enable].
- **Secondary swapping:** [SecondarySwapperEnableToggle][secondary-enable].
- **Expression:** [FaceExpressionEnableBothToggle][expr-enable] and [FaceExpressionBeforeTypeSelection][expr-position]. Advanced mode also checks the selected eyes/lips/brows/general branches.
- **Editor:** [FaceEditorEnableToggle][editor-enable] and [FaceEditorBeforeTypeSelection][editor-position].
- **Restorers:** [FaceRestorerEnableToggle][rest-enable], [FaceRestorerEnable2Toggle][rest2-enable], [FaceRestorerEnable2EndToggle][rest2-end]. Detailer: [FaceDetailerEnableToggle][detail-enable].
- **Frame enhancement:** [FrameEnhancerEnableToggle][enh-enable].

| Step | Model | Configuration — Settings Parameter(s) | Parameter Usage(s) | Model filename | MiB |
|---|---|---|---|---|---:|
| Before 1; detailer after 16 | RetinaFace | [DetectorModelSelection][det-def] = `RetinaFace` | [Detection call][det-use]; [model mapping][det-map]; [detailer][detail-det] | `det_10g.onnx` | 16.14 |
| Before 1; detailer after 16 | SCRFD 2.5G | [DetectorModelSelection][det-def] = `SCRFD` | [Detection call][det-use]; [model mapping][det-map]; [detailer][detail-det] | `scrfd_2.5g_bnkps.onnx` | 3.15 |
| Before 1; detailer after 16 | YOLOFace 8n | [DetectorModelSelection][det-def] = `Yolov8` | [Detection call][det-use]; [model mapping][det-map]; [detailer][detail-det] | `yoloface_8n.onnx` | 11.97 |
| Before 1; detailer after 16 | YuNet | [DetectorModelSelection][det-def] = `Yunet` | [Detection call][det-use]; [model mapping][det-map]; [detailer][detail-det] | `yunet_n_640_640.onnx` | 0.30 |
| Before 1; detailer after 16 | YOLOFace 11n VR180 | [DetectorModelSelection][det-def] = `Yolov11 VR180` | [Detection call][det-use]; [model mapping][det-map]; [detailer][detail-det] | `yoloface_11n-vr180.onnx` | 10.03 |
| Before 1; detailer after 16 | YOLOFace 12n VR180 | [DetectorModelSelection][det-def] = `Yolov12 VR180` | [Detection call][det-use]; [model mapping][det-map]; [detailer][detail-det] | `yoloface_12n-vr180.onnx` | 9.98 |
| 1, 3: recognition | Inswapper128 ArcFace | [RecognitionModelSelection][rec-def] = `Inswapper128ArcFace` | [Sequential recognition][rec-use]; [worker recognition][rec-worker] | `w600k_r50.onnx` | 166.31 |
| 1, 3: recognition | SimSwap ArcFace | [RecognitionModelSelection][rec-def] = `SimSwapArcFace` | [Sequential recognition][rec-use]; [worker recognition][rec-worker] | `simswap_arcface_model.onnx` | 199.24 |
| 1, 3: recognition | Ghost ArcFace | [RecognitionModelSelection][rec-def] = `GhostArcFace` | [Sequential recognition][rec-use]; [worker recognition][rec-worker] | `ghost_arcface_backbone.onnx` | 248.60 |
| 1, 3: recognition | CSCS ArcFace | [RecognitionModelSelection][rec-def] = `CSCSArcFace` | [Sequential recognition][rec-use]; [worker recognition][rec-worker] | `cscs_arcface_model.onnx` | 248.94 |
| CSCS recognition dependency | CSCS ID adapter | No separate control; follows `CSCSArcFace` recognition | [CSCS recognition calls adapter][cscs-use] | `cscs_id_adapter.onnx` | 249.94 |
| 2: landmarks | FaceLandmark5 | [LandmarkDetectModelSelection][land-def] = `5` | [Selection/gate][land-use]; [model mapping][land-map] | `res50.onnx` | 104.69 |
| 2: landmarks | FaceLandmark68 | [LandmarkDetectModelSelection][land-def] = `68` | [Selection/gate][land-use]; [model mapping][land-map] | `2dfan4.onnx` | 93.37 |
| 2: landmarks | FaceLandmark3d68 | [LandmarkDetectModelSelection][land-def] = `3d68` | [Selection/gate][land-use]; [model mapping][land-map] | `1k3d68.onnx` | 136.86 |
| 2: landmarks | FaceLandmark98 | [LandmarkDetectModelSelection][land-def] = `98` | [Selection/gate][land-use]; [model mapping][land-map] | `peppapig_teacher_Nx3x256x256.onnx` | 41.68 |
| 2: landmarks | FaceLandmark106 | [LandmarkDetectModelSelection][land-def] = `106` | [Selection/gate][land-use]; [model mapping][land-map] | `2d106det.onnx` | 4.73 |
| 2: landmarks | FaceLandmark203 | [LandmarkDetectModelSelection][land-def] = `203`; also forced by expression/editor/makeup or [AutoMouthExpressionEnableToggle][auto-mouth-def] | [Forced-203 conditions][force203-use]; [inference][force203-call] | `landmark.onnx` | 109.37 |
| 2: landmarks | FaceLandmark478 | [LandmarkDetectModelSelection][land-def] = `478` | [Selection/gate][land-use]; [model mapping][land-map] | `face_landmarks_detector_Nx3x256x256.onnx` | 4.73 |
| 2: 478 dependency | FaceBlendShapes | No separate control; follows [LandmarkDetectModelSelection][land-def] = `478` | [Dependency loading][blend-use] | `face_blendshapes_Nx146x2.onnx` | 1.78 |
| 2: landmarks | TUFA98 | [LandmarkDetectModelSelection][land-def] = `tufa98` | [Selection/gate][land-use]; [model mapping][land-map] | `tufa_vits8_256_98pt.onnx` | 136.88 |
| 2: landmarks | TUFA314 | [LandmarkDetectModelSelection][land-def] = `tufa314` | [Selection/gate][land-use]; [model mapping][land-map] | `tufa_vits8_256_314pt.onnx` | 137.83 |
| 2: landmarks | ORFormer98 | [LandmarkDetectModelSelection][land-def] = `orformer98` | [Selection/gate][land-use]; [model mapping][land-map] | `orformer_hgnet_wflw_98pt_256.onnx` | 71.31 |
| 2 / before 4: head boxes | DEIMv2 Wholebody49 Head | [LandmarkDetectModelSelection][land-def] = `hrffa`, or [YawNetEnableToggle][yaw-def]; landmark detection enabled | [HRFFA head detection][head-use]; [YawNet conditions][yaw-use] | `deimv2_hgnetv2_n_wholebody49_boxes_only_webgpu.onnx` | 15.24 |
| 2: landmarks | HRFFA | [LandmarkDetectModelSelection][land-def] = `hrffa` | [Head detection][head-use]; [model mapping][land-map] | `hrffa_vitt_ibug68_1x3x256x256.onnx` | 34.12 |
| Before 4; consumed at 5 | YawNet | [YawNetEnableToggle][yaw-def] AND [LandmarkDetectToggle][land-enable] | [Gate and yaw processing][yaw-use] | `yawnet_distill_128_unified_v6u_kappa_1x3x128x128.onnx` | 2.94 |
| 4: swapping | Inswapper128 | [SwapModelSelection][swap-def] or [SecondarySwapModelSelection][secondary-def] = `Inswapper128` | [Primary selector][swap-use]; [secondary selector][secondary-use] | `inswapper_128.fp16.onnx` | 264.82 |
| 4: swapping | AlphaFace | [SwapModelSelection][swap-def] or [SecondarySwapModelSelection][secondary-def] = `AlphaFace` | [Primary selector][swap-use]; [secondary selector][secondary-use] | `alphaface/alphaface_swapper_fused_norm.onnx` | 528.84 |
| 4: swapping | InStyleSwapper256 A | [SwapModelSelection][swap-def] or [SecondarySwapModelSelection][secondary-def] = `InStyleSwapper256 Version A` | [Primary selector][swap-use]; [secondary selector][secondary-use] | `InStyleSwapper256_Version_A.fp16.onnx` | 263.82 |
| 4: swapping | InStyleSwapper256 B | [SwapModelSelection][swap-def] or [SecondarySwapModelSelection][secondary-def] = `InStyleSwapper256 Version B` | [Primary selector][swap-use]; [secondary selector][secondary-use] | `InStyleSwapper256_Version_B.fp16.onnx` | 263.82 |
| 4: swapping | InStyleSwapper256 C | [SwapModelSelection][swap-def] or [SecondarySwapModelSelection][secondary-def] = `InStyleSwapper256 Version C` | [Primary selector][swap-use]; [secondary selector][secondary-use] | `InStyleSwapper256_Version_C.fp16.onnx` | 263.82 |
| 4: swapping | SimSwap512 | [SwapModelSelection][swap-def] = `SimSwap512` | [Primary selector][swap-use] | `simswap_512_unoff.onnx` | 228.09 |
| 4: swapping | GhostFace v1 | [SwapModelSelection][swap-def] = `GhostFace-v1` | [Primary selector][swap-use] | `ghost_unet_1_block.onnx` | 491.03 |
| 4: swapping | GhostFace v2 | [SwapModelSelection][swap-def] = `GhostFace-v2` | [Primary selector][swap-use] | `ghost_unet_2_block.onnx` | 704.51 |
| 4: swapping | GhostFace v3 | [SwapModelSelection][swap-def] = `GhostFace-v3` | [Primary selector][swap-use] | `ghost_unet_3_block.onnx` | 815.88 |
| 4: swapping | CSCS | [SwapModelSelection][swap-def] = `CSCS` | [Primary selector][swap-use] | `cscs_256.onnx` | 703.71 |
| 4: swapping | DeepFaceLive DFM | [SwapModelSelection][swap-def] = `DeepFaceLive (DFM)`; [DFMModelSelection][dfm-def] chooses file | [Selected file passed to pipeline][dfm-use] | User-selected `.dfm`; none installed in configured folder | — |
| 6, 9, 11; editor at 12 | LivePortrait Motion Extractor | [FaceExpressionModeSelection][expr-mode] = `Simple`/`Advanced`; or [FaceEditorEnableToggle][editor-enable] | [Expression dispatch][expr-use]; [motion extraction][motion-use] | `liveportrait_onnx/motion_extractor.onnx` | 107.43 |
| 6, 9, 11; editor at 12 | LivePortrait Appearance Extractor | [FaceExpressionModeSelection][expr-mode] = `Simple`/`Advanced`; or [FaceEditorEnableToggle][editor-enable] | [Expression dispatch][expr-use]; [appearance extraction][appearance-use] | `liveportrait_onnx/appearance_feature_extractor.onnx` | 3.20 |
| 6, 9, 11; editor at 12 | LivePortrait Eye Retargeting | Expression: [FaceExpressionEyesToggle][expr-eyes] + [FaceExpressionRetargetingEyesBothEnableToggle][eye-retarget-def]. Editor: [EyesOpenRatioDecimalSlider][eye-ratio-def] | [Expression eye branch][eye-use]; [editor eye branch][editor-eye-use] | `liveportrait_onnx/stitching_eye.onnx` | 0.55 |
| 6, 9, 11; editor at 12 | LivePortrait Lip Retargeting | Simple: [FaceExpressionNormalizeLipsEnableToggle][lip-normalize-def]. Advanced: [FaceExpressionLipsToggle][expr-lips] + [FaceExpressionRetargetingLipsBothEnableToggle][lip-retarget-def]. Editor: [LipsOpenRatioDecimalSlider][lip-ratio-def] | [Simple normalization][lip-simple-use]; [Advanced retargeting][lip-use]; [editor lip branch][editor-lip-use] | `liveportrait_onnx/stitching_lip.onnx` | 0.14 |
| 6, 9, 11; editor at 12 | LivePortrait Stitching | [FaceExpressionModeSelection][expr-mode] = `Simple`/`Advanced`; or [FaceEditorEnableToggle][editor-enable] | [Expression stitching][stitch-use]; [editor stitching][editor-stitch-use] | `liveportrait_onnx/stitching.onnx` | 0.17 |
| 6, 9, 11; editor at 12 | LivePortrait Warping/SPADE | [FaceExpressionModeSelection][expr-mode] = `Simple`/`Advanced`; or [FaceEditorEnableToggle][editor-enable] | [Expression decoding][warp-use]; [editor decoding][editor-warp-use] | `liveportrait_onnx/warping_spade.onnx` | 401.72 |
| 6, 9, 11: expression | PerformRecast Appearance Extractor | [FaceExpressionModeSelection][expr-mode] = `Recast` | [Recast dispatch][expr-use] | `performrecast_onnx/appearance_feature_extractor.onnx` | 341.67 |
| 6, 9, 11: expression | PerformRecast Motion Extractor | [FaceExpressionModeSelection][expr-mode] = `Recast` | [Recast dispatch][expr-use] | `performrecast_onnx/motion_extractor.onnx` | 107.85 |
| 6, 9, 11: expression | PerformRecast Warping Module | [FaceExpressionModeSelection][expr-mode] = `Recast` | [Recast dispatch][expr-use] | `performrecast_onnx/warping_module.onnx` | 195.58 |
| 6, 9, 11: expression | PerformRecast SPADE Generator | [FaceExpressionModeSelection][expr-mode] = `Recast` | [Recast dispatch][expr-use] | `performrecast_onnx/spade_generator.onnx` | 327.65 |
| Between 6–7, 9–10; late 14 | Ref-LDM VAE Encoder | [DenoiserUNetEnableBeforeRestorersToggle][den-before-def], [DenoiserAfterFirstRestorerToggle][den-first-def], [DenoiserAfterRestorersToggle][den-after-def] | [Before][den-before-use]; [after first][den-first-use]; [after restorers][den-after-use] | `ref_ldm_vae_encoder.onnx` | 88.19 |
| Between 6–7, 9–10; late 14 | Ref-LDM UNet | [DenoiserUNetEnableBeforeRestorersToggle][den-before-def], [DenoiserAfterFirstRestorerToggle][den-first-def], [DenoiserAfterRestorersToggle][den-after-def] | [Before][den-before-use]; [after first][den-first-use]; [after restorers][den-after-use] | `ref_ldm_unet_external_kv.onnx` | 449.81 |
| Between 6–7, 9–10; late 14 | Ref-LDM VAE Decoder | [DenoiserUNetEnableBeforeRestorersToggle][den-before-def], [DenoiserAfterFirstRestorerToggle][den-first-def], [DenoiserAfterRestorersToggle][den-after-def] | [Before][den-before-use]; [after first][den-first-use]; [after restorers][den-after-use] | `ref_ldm_vae_decoder.onnx` | 129.87 |
| 7, 10/13; detailer after 16 | GFPGAN v1.4 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `GFPGAN-v1.4` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `GFPGANv1.4.onnx` | 324.50 |
| 7, 10/13; detailer after 16 | GFPGAN 1024 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `GFPGAN-1024` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `gfpgan-1024.onnx` | 348.93 |
| 7, 10/13; detailer after 16 | CodeFormer | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `CodeFormer` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `codeformer_fp16.onnx` | 179.84 |
| 7, 10/13; detailer after 16 | GPEN 256 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `GPEN-256` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `GPEN-BFR-256.onnx` | 72.14 |
| 7, 10/13; detailer after 16 | GPEN 512 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `GPEN-512` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `GPEN-BFR-512.onnx` | 271.00 |
| 7, 10/13; detailer after 16 | GPEN 1024 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `GPEN-1024` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `GPEN-BFR-1024.onnx` | 271.80 |
| 7, 10/13; detailer after 16 | GPEN 2048 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `GPEN-2048` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `GPEN-BFR-2048.onnx` | 272.14 |
| 7, 10/13; detailer after 16 | RestoreFormer++ | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `RestoreFormer++` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `RestoreFormerPlusPlus.fp16.onnx` | 141.36 |
| 7, 10/13; detailer after 16 | VQFR v2 | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `VQFR-v2` | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [model dispatch][rest-dispatch]; [model mapping][rest-map] | `VQFRv2.fp16.onnx` | 342.87 |
| 7, 10/13; detailer after 16 | OSDFace Prompt Encoder | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `OSDFace`; no separate submodel toggle | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [OSDFace model group][osd-group] | `osdface/prompt_encoder.onnx` | 114.88 |
| 7, 10/13; detailer after 16 | OSDFace VAE Encoder | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `OSDFace`; no separate submodel toggle | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [OSDFace model group][osd-group] | `osdface/vae_encoder.onnx` | 130.40 |
| 7, 10/13; detailer after 16 | OSDFace UNet | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `OSDFace`; no separate submodel toggle | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [OSDFace model group][osd-group] | `osdface/unet.onnx` + `osdface/unet.onnx.data` | 3,304.27 |
| 7, 10/13; detailer after 16 | OSDFace VAE Decoder | [FaceRestorerTypeSelection][rest-def] / [FaceRestorerType2Selection][rest2-def] / [FaceDetailerRestorerTypeSelection][detail-def] = `OSDFace`; no separate submodel toggle | [Slot 1][rest-use]; [slot 2][rest2-use]; [end slot][rest-end-use]; [detailer][detail-use]; [OSDFace model group][osd-group] | `osdface/vae_decoder.onnx` | 188.89 |
| 8: occlusion; mouth protection | Occluder | [OccluderEnableToggle][occ-def]; mouth-overlay path also requires [MouthParserStretchToggle][mouth-def] and [MouthParserStretchOriginalToggle][mouth-original-def] | [Main occluder][occ-use]; [mouth obstacle mask][mouth-obstacle-use] | `occluder.onnx` | 54.66 |
| Before 7 / 14: mouth enhancement | FaceParser ResNet34 | [MouthParserStretchToggle][mouth-def]; [MouthParserStretchOriginalToggle][mouth-original-def] adds original-face parsing; [MouthParserStretchAfterToggle][mouth-after-def] sets position | [Mouth parser calls][mouth-use]; [before/after choice][mouth-position-use] | `faceparser_resnet34.onnx` | 89.30 |
| 8: face parsing; 14: ending parser | FaceParser ResNet34 | [FaceParserEnableToggle][parser-def]; [FaceParserEndToggle][parser-end-def] controls ending pass | [Parser requirements][parser-use]; [ending pass][parser-end-use] | `faceparser_resnet34.onnx` | 89.30 |
| 8: XSeg Mouth regions | FaceParser ResNet34 | [DFLXSegEnableToggle][xseg-def] AND [XSegMouthEnableToggle][xmouth-def], with [DFLXSegSizeSlider][xsize-def] ≠ [DFLXSeg2SizeSlider][xsize2-def] | [Mouth-parser condition][xmouth-use] | `faceparser_resnet34.onnx` | 89.30 |
| 8: XSeg mouth/lip protection | FaceParser ResNet34 | [XSegExcludeInnerMouthToggle][xprotect-def]; XSeg must be enabled to consume its protection mask | [Parser requirement][parser-use]; [XSeg consumption][xseg-use] | `faceparser_resnet34.onnx` | 89.30 |
| 8: occluder tongue protection | FaceParser ResNet34 | [OccluderEnableToggle][occ-def] + [OccluderTonguePriorityToggle][tongue-def] | [Occluder protection branch][tongue-use] | `faceparser_resnet34.onnx` | 89.30 |
| 8 → 12: texture/difference exclusion regions | FaceParser ResNet34 | ([TransferTextureEnableToggle][texture-def] OR [DifferencingEnableToggle][diff-def]) AND [ExcludeMaskEnableToggle][exclude-def] | [Parser requirement][parser-use] | `faceparser_resnet34.onnx` | 89.30 |
| 8: text mask | CLIP ViT-B/16 backbone | [ClipEnableToggle][clip-def]; text supplied through `ClipText` | [CLIP gate][clip-use]; [backbone loading][clip-backbone-use] | `C:/Users/shoji/.cache/clip/ViT-B-16.pt` | 334.58 |
| 8: text mask | CLIPSeg prediction weights | [ClipEnableToggle][clip-def]; text supplied through `ClipText` | [CLIP gate][clip-use]; [weights loading][clip-weights-use] | `rd64-uni-refined.pth` | 4.50 |
| 8: XSeg / XSeg Mouth | DFL XSeg | [DFLXSegEnableToggle][xseg-def]; [XSegMouthEnableToggle][xmouth-def] enables mouth-specific processing; [XSegExcludeInnerMouthToggle][xprotect-def] enables protection | [XSeg gate and mouth inputs][xseg-use] | `XSeg_model.onnx` | 67.08 |
| 12: texture exclusion / differencing | VGG combined features | [TransferTextureEnableToggle][texture-def] + [ExcludeOriginalVGGMaskEnableToggle][vgg-def]; or [DifferencingEnableToggle][diff-def]. [ExcludeVGGMaskEnableToggle][vgg-threshold-def] controls exclusion threshold use | [Texture VGG call][vgg-use]; [differencing call][diff-use] | `vgg_combo_relu3_3_relu3_1.onnx` | 6.62 |
| 14: hair matting | MODNet | [HairMattingEnableToggle][hair-def] | [Hair-matting gate][hair-use] | `modnet_photographic_portrait_matting.onnx` | 24.70 |
| 16: makeup | FaceParser ResNet34 | [FaceMakeupEnableToggle][makeup-face-def], [HairMakeupEnableToggle][makeup-hair-def], [EyeBrowsMakeupEnableToggle][makeup-brow-def], or [LipsMakeupEnableToggle][makeup-lip-def] | [Makeup gate and parser path][makeup-use] | `faceparser_resnet34.onnx` | 89.30 |
| After 17 | RealESRGAN ×2 Plus | [FrameEnhancerTypeSelection][enh-def] = `RealEsrgan-x2-Plus` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `RealESRGAN_x2plus.fp16.onnx` | 32.06 |
| After 17 | RealESRGAN ×4 Plus | [FrameEnhancerTypeSelection][enh-def] = `RealEsrgan-x4-Plus` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `RealESRGAN_x4plus.fp16.onnx` | 32.09 |
| After 17 | RealESR General ×4v3 | [FrameEnhancerTypeSelection][enh-def] = `RealEsr-General-x4v3` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `realesr-general-x4v3.onnx` | 4.65 |
| After 17 | BSRGAN ×2 | [FrameEnhancerTypeSelection][enh-def] = `BSRGan-x2` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `BSRGANx2.fp16.onnx` | 31.98 |
| After 17 | BSRGAN ×4 | [FrameEnhancerTypeSelection][enh-def] = `BSRGan-x4` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `BSRGANx4.fp16.onnx` | 32.09 |
| After 17 | UltraSharp ×4 | [FrameEnhancerTypeSelection][enh-def] = `UltraSharp-x4` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `4x-UltraSharp.fp16.onnx` | 32.09 |
| After 17 | UltraMix ×4 | [FrameEnhancerTypeSelection][enh-def] = `UltraMix-x4` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `4x-UltraMix_Smooth.fp16.onnx` | 32.09 |
| After 17 | DDColor Artistic | [FrameEnhancerTypeSelection][enh-def] = `DDColor-Artistic` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `ddcolor_artistic.onnx` | 870.12 |
| After 17 | DDColor | [FrameEnhancerTypeSelection][enh-def] = `DDColor` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `ddcolor.onnx` | 870.12 |
| After 17 | DeOldify Artistic | [FrameEnhancerTypeSelection][enh-def] = `DeOldify-Artistic` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `ColorizeArtistic.fp16.onnx` | 121.47 |
| After 17 | DeOldify Stable | [FrameEnhancerTypeSelection][enh-def] = `DeOldify-Stable` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `ColorizeStable.fp16.onnx` | 416.28 |
| After 17 | DeOldify Video | [FrameEnhancerTypeSelection][enh-def] = `DeOldify-Video` | [Enable gate][enh-gate]; [selector dispatch][enh-use] | `ColorizeVideo.fp16.onnx` | 416.28 |
| Source preparation | Ref-LDM checkpoint | Any denoiser pass enabled: [DenoiserUNetEnableBeforeRestorersToggle][den-before-def], [DenoiserAfterFirstRestorerToggle][den-first-def], [DenoiserAfterRestorersToggle][den-after-def]; reference KV missing | [KV preparation condition][kv-use]; [checkpoint loading][kv-load] | `ref-ldm_embedding/ckpts/refldm.ckpt` | 1,117.09 |
| Source preparation | VQGAN checkpoint | Any denoiser pass enabled: [DenoiserUNetEnableBeforeRestorersToggle][den-before-def], [DenoiserAfterFirstRestorerToggle][den-first-def], [DenoiserAfterRestorersToggle][den-after-def]; reference KV missing | [KV preparation condition][kv-use]; [checkpoint loading][kv-load] | `ref-ldm_embedding/ckpts/vqgan.ckpt` | 742.48 |
| Source preparation | Face Re-aging | [FaceReagingEnableToggle][age-def]; [FaceReagingSourceAgeSlider][age-source-def]; [FaceReagingTargetAgeSlider][age-target-def] | [Apply re-aging][age-use]; [processed-frame embedding selection][age-consume] | `face_reaging.onnx` | 118.46 |

[land-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:682
[detail-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:26
[enh-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:905
[det-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:627
[rec-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:615
[land-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:690
[yaw-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:734
[detail-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:34
[enh-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/settings_layout_data.py:913
[secondary-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:114
[swap-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:10
[secondary-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:120
[dfm-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:86
[occ-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:422
[mouth-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:715
[mouth-original-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:721
[mouth-after-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:784
[parser-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:816
[parser-end-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:824
[xseg-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:449
[xmouth-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:554
[xsize-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:473
[xsize2-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:562
[xprotect-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:457
[tongue-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:441
[texture-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:1272
[diff-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:1211
[exclude-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:1432
[clip-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:617
[vgg-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:1353
[vgg-threshold-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:1383
[hair-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:649
[age-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:2049
[age-source-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:2056
[age-target-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/swapper_layout_data.py:2068
[expr-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:292
[expr-position]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:285
[rest-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:6
[rest2-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:147
[rest2-end]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:155
[auto-mouth-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:973
[expr-mode]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:300
[expr-eyes]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:567
[eye-retarget-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:667
[lip-normalize-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:528
[expr-lips]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:779
[lip-retarget-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:827
[rest-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:14
[rest2-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/common_layout_data.py:163
[editor-enable]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:47
[editor-position]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:6
[eye-ratio-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:70
[lip-ratio-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:82
[makeup-face-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:270
[makeup-hair-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:321
[makeup-brow-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:372
[makeup-lip-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/face_editor_layout_data.py:423
[den-before-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/denoiser_layout_data.py:89
[den-first-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/denoiser_layout_data.py:171
[den-after-def]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/denoiser_layout_data.py:253
[det-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/video_utils/sequential_detector.py:181
[rec-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/video_utils/sequential_detector.py:207
[land-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/video_utils/sequential_detector.py:104
[force203-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/video_utils/sequential_detector.py:108
[force203-call]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/video_utils/sequential_detector.py:390
[head-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/video_utils/sequential_detector.py:375
[rec-worker]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_standard.py:375
[yaw-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_standard.py:405
[dfm-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_standard.py:724
[kv-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_standard.py:623
[age-consume]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_standard.py:674
[det-map]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_detectors.py:96
[detail-det]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_detailer.py:117
[detail-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_detailer.py:110
[cscs-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_swappers.py:361
[land-map]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_landmark_detectors.py:182
[blend-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_landmark_detectors.py:837
[swap-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:1840
[secondary-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:1883
[expr-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2352
[den-before-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2410
[den-first-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2869
[den-after-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:3542
[rest-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2446
[rest2-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2882
[rest-end-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:3409
[occ-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2467
[mouth-position-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2421
[parser-end-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:3463
[xseg-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2640
[clip-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:2547
[vgg-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:3076
[diff-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:3245
[hair-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker_pipeline.py:3697
[motion-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:215
[appearance-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:258
[eye-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:725
[editor-eye-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:1363
[lip-simple-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:600
[lip-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:799
[editor-lip-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:1384
[stitch-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:263
[editor-stitch-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:1416
[warp-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:898
[editor-warp-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:1421
[makeup-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_edits.py:1468
[rest-dispatch]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_restorers.py:349
[rest-map]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_restorers.py:39
[osd-group]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_restorers.py:19
[mouth-obstacle-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_masks.py:654
[mouth-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_masks.py:633
[parser-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_masks.py:756
[xmouth-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_masks.py:768
[tongue-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_masks.py:1266
[clip-weights-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_masks.py:1738
[clip-backbone-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/external/clipseg.py:86
[enh-gate]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/workers/frame_worker.py:709
[enh-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/frame_enhancers.py:417
[kv-load]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/processors/face_denoiser.py:295
[age-use]: /S:/Drives/VisoMatrix/Data/Packages/visomaster_fusion_portable/VisoMaster-Fusion/app/ui/widgets/actions/control_actions.py:800
