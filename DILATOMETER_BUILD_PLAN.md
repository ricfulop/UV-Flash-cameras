# 3D Wire Flash Dilatometer Build Plan

## Revised Recommendation

Build this as an MIT-paper-grade custom wire dilatometer around the cameras, Flash camera app, optical tables, and optomechanics already in hand.

- **Primary path: two-camera 3D wire dilatometer inside the existing Flash camera app.** Use the Basler and Allied Vision IMX487-class cameras, hardware-trigger both cameras from the same TTL source, record OES timestamps in parallel, and save calibrated raw frames plus metadata.
- **Optical baseline: 0.16X SilverTL-class telecentric lenses with 470 nm strobed backlit silhouette imaging.** This prioritizes full clip-to-clip wire length/arc-length over high-precision diameter CTE. A 365 nm UV branch remains optional, but not the v1 build.
- **Measurement priority for wires: length and width increase in 3D between the fixed clips.** The primary outputs are the 3D centerline arc length between clip fiducials, projected and reconstructed end-to-end length, transverse width/diameter versus axial coordinate, centerline curvature/bowing, and any local necking/swelling. This is a stereo silhouette/edge metrology problem first, not a full-field DIC problem.
- **3D model output: time-varying tube, not DIC-first surface reconstruction.** Reconstruct a calibrated 3D centerline plus radius/elliptical width along the wire, then export a per-frame mesh/tube with arc length, bowing, width, and swelling fields.
- **Measurement path for foils: segmentation first, DIC only if texture is valid.** A 5 mm x 50 mm foil can support stereo-DIC only if natural texture is stable and non-perturbing; otherwise use edges, outline, bowing, and fiducials.
- **Gauge length is a design knob, but fixed clips define the reference endpoints.** Mechanically, keep the fixed clips as the length reference. Optically, use either a full clip-to-clip view for total length or a higher-magnification sub-gauge view for diameter/width validation. If clip spacing is long, use two operating modes rather than forcing one lens to do both jobs.

## Camera And Optics Baseline

- Flash camera app repo: `/Users/ricfulop/UV Flash Cameras/UV-Flash-cameras`.
- Confirmed Basler runtime camera: **Basler ace 2 X a2A2840-48umUV**, serial `40775503`, pypylon/Pylon backend, Mono12 working in the app. Vendor specs: Sony IMX487, 2840 x 2840 default pixels, 2.74 um pixels, 7.78 mm x 7.78 mm sensor, 2/3 inch format, global shutter, USB3, ~48 fps, hardware trigger, UV 200-400 nm.
- Intended/likely Allied Vision companion: **Allied Vision Alvium 1800 U-812 UV** or equivalent, VmbPy/Vimba X backend. Vendor specs: Sony IMX487, 2848 x 2848 pixels, 2.74 um pixels, 2/3 inch format, global shutter, USB3, ~50-51 fps, 200-1100 nm sensitivity. The Allied serial still needs to be filled in after VmbPy/Vimba X is installed.
- Spec cleanup: the original Flash camera spec says Sony IMX478, but the detected Basler and the likely Allied UV model are **IMX487**. Treat IMX487 as the build baseline.
- Because these UV cameras may also see visible/NIR unless filtered, the camera must be treated as **sensor + lens + filter stack**, not just sensor response.
- Selected v1 lens: **0.16X SilverTL-class visible telecentric pair**, or equivalent. The Edmund #56-675 reference lens has 177 mm working distance and 40 mm x 30 mm FOV on a 1/2 inch sensor; it may vignette on the 2/3 inch IMX487 cameras, so quote/verify a true 2/3 inch equivalent if the full ~48 mm FOV is required.
- UV lenses are a separate branch. Use UV-transmissive quartz/fused-silica C-mount lenses for true 365 nm or deeper UV. EHD lists quartz UV lenses for IMX487 2/3 inch sensors, including fixed focal lengths and a 1X telecentric option; this is useful for high-resolution UV validation, not full-sample 48 mm v1 imaging.

## Gauge Length And Telecentric Lens Sizing

Use the IMX487-class UV camera geometry as the baseline: approximately 2840 x 2840 px, 2.74 um pixels, and a 7.78 mm active sensor width. For a telecentric lens, object-space FOV is approximately `7.78 mm / magnification`, and object-space pixel size is `FOV / 2840`.

| Telecentric magnification | Approx. FOV | Pixel scale | 250 um wire diameter | Best use |
|---:|---:|---:|---:|---|
| 1.0X | 7.8 mm | 2.7 um/px | 91 px | Best wire width/diameter validation |
| 0.75X | 10.4 mm | 3.7 um/px | 68 px | Short-gauge wire length + width |
| 0.5X | 15.6 mm | 5.5 um/px | 46 px | Practical wire production mode |
| 0.33X | 23.6 mm | 8.3 um/px | 30 px | Long wire centerline/length mode |
| 0.25X | 31.1 mm | 11.0 um/px | 23 px | Overview mode; width marginal |
| 0.16X | 48.6 mm | 17.1 um/px | 15 px | Full 50 mm clip-to-clip length only |

Measurement interpretation:

- **Length between fixed clips:** can be measured in a full-gauge view by reconstructing the 3D wire centerline and integrating arc length between clip fiducials. Even at ~0.16X, endpoint/centerline length changes should be measurable because Flash expansion is large relative to the pixel scale.
- **Width/diameter increase:** needs a shorter FOV. At a 50 mm FOV, the 250 um wire is only ~15 px wide; subpixel edges may detect large swelling, but CTE-scale diameter changes are marginal. For credible width expansion, use 0.5X to 1.0X, giving ~46-91 px across the wire.
- **Selected v1 MIT-paper mode:** use the **0.16X full-sample view** to capture fixed clips and reconstruct full 3D arc length/bowing over the sample. Claim precise length/shape and large width changes. Keep the 0.5X to 1.0X short-FOV modes as future upgrades if sub-percent diameter expansion becomes central.

Recommended lens purchases/quotes:

- **Selected baseline pair: 0.16X SilverTL-class telecentric lenses for full-sample imaging.** The target is to see a ~48 mm sample/clip span in one view with the existing IMX487-class cameras. The Edmund Optics #56-675 0.16X SilverTL is the reference candidate, with 177 mm working distance and 40 mm x 30 mm FOV on a 1/2 inch sensor. However, Edmund lists this model as **maximum 1/2 inch sensor format**, so it may vignette on the 2/3 inch IMX487 cameras before reaching the theoretical 48.6 mm FOV. Treat it as acceptable if a ~40 mm horizontal FOV is enough or if we can use a centered ROI; otherwise quote an equivalent 0.16X telecentric lens with a true 2/3 inch image circle.
- **Keep 0.5X to 1.0X alternatives for future width-resolution work.** A 0.16X full-sample view gives only ~15 px across a 250 um wire on the current cameras. This is enough for centerline/arc-length and large swelling, but not ideal for precise width. The table above stays in the plan so we can move to 0.5X or 1.0X if later runs require higher-confidence width/diameter changes.
- **Full-sample mode decision:** use the 0.16X SilverTL-class pair for the first two-camera top/front setup, with the explicit measurement claim limited to full 3D length/arc-length, bowing, and large width changes.

## ASI6200-Class Full-Frame Comparison

An ASI6200-equivalent camera uses a Sony IMX455-class full-frame sensor: 9576 x 6388 px, 3.76 um pixels, 36 mm x 24 mm active area, and 43.3 mm diagonal. Compared with the IMX487 UV cameras, the full-frame sensor gives much higher spatial sampling at the same object FOV, but requires much larger and more expensive telecentric lenses with a ~43 mm image circle.

For the ASI6200-class horizontal sensor width, object-space FOV is approximately `36 mm / magnification`.

| Telecentric magnification | Approx. horizontal FOV | Pixel scale | 250 um wire diameter | Best use |
|---:|---:|---:|---:|---|
| 1.0X | 36 mm | 3.76 um/px | 66 px | High-resolution partial/full wire view |
| 0.75X | 48 mm | 5.01 um/px | 50 px | Best full 48 mm sample mode |
| 0.5X | 72 mm | 7.52 um/px | 33 px | Full sample plus generous clip margins |
| 0.38X | 94.7 mm | 9.89 um/px | 25 px | Large-format overview; Opto Engineering TC16M096-class |
| 0.25X | 144 mm | 15.0 um/px | 17 px | Very large overview; width marginal |
| 0.16X | 225 mm | 23.5 um/px | 11 px | Too wide for this wire-width problem |

Interpretation:

- For a **48 mm sample**, a full-frame 0.75X telecentric system gives ~5.0 um/px and ~50 px across a 250 um wire. That is roughly **3.4x better width sampling** than the current IMX487 cameras at 0.16X over ~48 mm.
- Full-frame telecentric optics are the expensive part. Opto Engineering's TC16M series is an example of full-frame telecentric lenses for 43.3 mm image circles; a 0.75X TC16M048-class lens gives ~48 mm x 32 mm FOV on full frame, but is physically large, M58-mounted, and around kilogram scale.
- ASI6200-class cameras are not a drop-in replacement for high-speed Flash metrology: full-resolution frame rate is low, and rolling-shutter behavior/timing control must be checked. The full-frame option is attractive for **high-resolution slower/quasi-static or event-integrated measurements**, not necessarily for fast Flash onset unless ROI frame rate and trigger synchronization are adequate.
- Planning decision: proceed with the 0.16X SilverTL-class pair on the existing cameras for v1, but keep the full-frame 0.75X telecentric option as the high-resolution upgrade path if width/diameter sensitivity becomes the limiting factor.

## Lighting And Filters For V1

The selected 0.16X SilverTL-class lens pushes the v1 geometry measurement toward visible blue active imaging, not true UV. The Edmund SilverTL reference family is coated for the visible band, so use **470 nm blue strobed silhouette imaging** as the baseline. Treat 365 nm UV as a separate optical experiment requiring UV-transmitting lenses, not the first full-sample telecentric build.

Baseline v1 stack:

- **Illumination wavelength:** 470 nm blue LED, strobed from the same timing source as the cameras. 450 nm is also acceptable if the LED/filter/lens combination is brighter, but 470 nm is a common high-temperature DIC band and is well supported by machine-vision filters.
- **Illumination geometry:** backlight/silhouette first, front/coaxial second. Put a blue LED backlight or line light opposite each camera so the wire appears as a dark silhouette against a narrow-band blue field. This is better for length/width extraction than speckle-style front lighting.
- **Camera filters:** one matched filter per camera. Start with either a narrow 470 nm bandpass, e.g. 470/10 or 470/25 with OD4 blocking, or a machine-vision BP470-class filter if more light is needed.
- **Blocking requirement:** OD4 minimum outside the passband; OD5-OD6 preferred if the Flash continuum/plasma glow saturates the sensor. Because the Allied/Basler UV sensors can see visible/NIR outside the UV band, do not rely on the camera to reject unwanted light.
- **Neutral density:** buy ND filters for the selected passband so Flash-off alignment, Flash-on recording, and saturated/glowing samples can share the same optical geometry without changing exposure too much.
- **Lighting vendor class:** CCS UV3/VL3, Advanced Illumination, or Smart Vision Lights class strobed machine-vision lights. For 470 nm use standard blue machine-vision bars, rings, or backlights from the same vendors.

Secondary filter/lighting modes to keep available:

- **405 nm near-UV/violet:** useful if plasma/OES shows a cleaner window near 405 nm and the chosen lens transmits enough. Use 405/10 or 405/25 OD4 filters plus 405 nm strobe illumination.
- **365 nm UV:** only for a UV-lens branch using quartz/fused-silica optics. Use 365 nm LED illumination, 365/10 or 365/25 filters, and visible/NIR blocking. UV-DIC literature supports higher-temperature operation at 1250-1600 C, but this is not the v1 SilverTL baseline.
- **Existing 780/810 nm filters:** keep for plasma/emission imaging, not primary geometry. These bands overlap strong plasma lines and are likely worse for silhouette metrology during Flash.

Minimum bill of materials for optical filtering/lighting:

- Two 470 nm camera filters, preferably 25 mm or lens-thread matched, OD4 or better.
- Two 470 nm strobed backlights or high-power line/bar lights, one for the top view and one for the front view.
- Two LED drivers/controllers with TTL trigger input, or one multi-channel strobe controller with per-channel timing.
- ND filter set for each camera path.
- Diffusers/backlight plates that do not fluoresce strongly under blue/UV.
- Filter holders or lens-tube adapters compatible with the SilverTL filter thread and the camera/lens mounts.
- Optional 405 nm filter/light pair for passband scouting.

## UV Lens Options

True UV imaging is possible with the IMX487 cameras, but it changes the lens choice:

- **Confirmed UV-compatible option:** EHD Imaging lists UV-HR quartz C-mount lenses designed for Sony IMX487-class 2/3 inch sensors, optimized over 200-1000 nm, with 180 lp/mm resolution. Their UV-HR line includes fixed focal lengths and a **1X telecentric lens with 101 mm working distance**. This is the cleanest path for 365 nm / 405 nm UV validation, but it gives a short FOV near the sensor width, not the 48 mm full-sample view.
- **UV non-telecentric options:** Myutron UV C-mount lenses for IMX487-class cameras are available in 16, 25, 35, 50, and 100 mm focal lengths. These are useful for UV overview/scouting, but not as dimensionally clean as telecentric optics.
- **Near-UV / violet telecentric options:** Some telecentric lenses cover roughly 380-900 nm. These may work at 405 nm but should not be assumed to work at 365 nm without transmission data.
- **Full 48 mm UV telecentric gap:** no clean off-the-shelf 0.16X, 2/3 inch, 365 nm UV telecentric option has been identified yet. If we need full 48 mm FOV in true UV, expect a custom/specialty quote or a larger-format UV telecentric system.

Decision: use **470 nm SilverTL-class full-sample imaging for v1**, and keep **EHD 1X UV telecentric** as a separate high-resolution UV validation branch.

## Open-Source 3D-DIC Tool Pipeline

Open-source stereo/3D-DIC exists, but it requires texture or speckles. For real Flash wire runs, avoid sample-applied speckles; therefore the wire pipeline remains silhouette/edge based. Use 3D-DIC mainly for foils, calibration coupons, or natural-texture cases.

Candidate tools:

- **DICe:** open-source C++ DIC engine with 2D and stereo DIC support, command-line execution, GUI basics, MPI/threaded parallelism, and `libdice` integration. Best candidate for a backend wrapped by the Flash camera app.
- **OpenCorr:** open-source C++ library for 2D, 3D/stereo DIC, and volumetric DIC, with stereo reconstruction and epipolar-search modules. Best for method development and custom integration.
- **DuoDIC:** open-source MATLAB toolbox for two-camera stereo 3D-DIC using Ncorr and MATLAB calibration. Good validation/reference path if MATLAB is acceptable.
- **MultiDIC:** open-source MATLAB toolbox for multi-view 3D-DIC with 3+ cameras. Useful if we later add an oblique third camera.
- **Pyvale:** promising Python DIC work, but current public material describes 2D DIC with stereo planned, so it is not the near-term 3D backend.

Recommended software split:

- **Wire:** OpenCV/custom stereo silhouette pipeline for edges, centerline, diameter, and 3D arc length.
- **Foil or validation coupon:** DICe/OpenCorr for stereo DIC if there is stable natural or non-perturbing texture.
- **Cross-check:** DuoDIC/MultiDIC on saved image pairs when we want an independent MATLAB comparison.

### Hugh Herr / MultiDIC Decision

The Hugh Herr-associated tool is **MultiDIC**: the open-source MATLAB multi-view 3D-DIC toolbox by Solav, Moerman, Jaeger, Genovese, and Herr. It reconstructs 3D surfaces from multiple stereo image pairs by correlating surface texture through Ncorr and merging reconstructed meshes.

Use MultiDIC for:

- validation on speckled calibration coupons,
- foils with stable natural or non-perturbing texture,
- multi-camera surface reconstruction if we later add 3+ cameras,
- an independent MATLAB cross-check of a saved dataset.

Do not use MultiDIC as the primary real-Flash wire pipeline because:

- the active 250 um wire should not be speckled or coated,
- the wire surface is smooth, glowing, and likely lacks unique DIC subsets,
- top/front orthogonal views do not see the same surface patch in the way a stereo-DIC pair expects,
- full 48 mm v1 imaging gives only ~15 px across the wire, which is enough for silhouette centerline but weak for surface DIC.

For the wire, generate the 3D model as a **time-varying tube**: calibrated 3D centerline plus radius/elliptical width along the axis. The model output should be a mesh or spline tube with per-frame fields: arc length, end-to-end length, centerline curvature, width/diameter, and local swelling/necking.

## Optical And Experimental Constraints

- Use **hardware-triggered global-shutter cameras**. Temporal mismatch between stereo views causes 3D reconstruction error, and rolling shutter introduces line-dependent timing distortion during motion; hardware trigger/TTL synchronization is the clean route.
- Synchronize the cameras, illumination pulses, electrical trace, and OES acquisition with a common timebase. The OES span of 200 nm to 1.7 um is a strength: use it to choose imaging passbands that avoid the worst plasma/surface emission lines in the actual Flash spectrum.
- Use **narrow-band UV/blue illumination plus matching bandpass filters** to suppress blackbody/plasma glow. For v1, this means 470 nm active illumination and OD4+ filtering.
- Avoid sample-applied speckles during real Flash runs unless a control proves they do not perturb onset, current localization, emissivity, surface chemistry, or reduction kinetics. For the primary MIT-paper wire measurement, use non-contact optical features: wire silhouette, left/right edges, centerline, clip/fiducial motion, natural surface texture where available, and off-sample fiducials.
- Put a **fiducial next to the target** in the same optical volume: alumina/sapphire/quartz carrier with etched or deposited high-contrast dots. Use it for scale, drift, heat-haze diagnostics, camera pose checks, and registration to current/voltage/temperature data.

## Physical Setup

Use two cameras in orthogonal or near-orthogonal views:

- **Front camera:** looks horizontally at the wire and measures the `x-z` projection: axial coordinate, vertical sag/bowing, and front-view apparent diameter.
- **Top camera:** looks down at the wire and measures the `x-y` projection: axial coordinate, lateral bowing, and top-view apparent diameter.
- **Shared coordinate system:** `x` is between clips, `y` is lateral/front-back, and `z` is vertical. The reconstructed wire centerline is `r(x) = [x, y(x), z(x)]`.

### Camera Positions, Working Distance, And Focus

Use the straight, room-temperature wire centerline as the nominal object plane for both cameras.

| Element | Position relative to sample | Purpose |
|---|---|---|
| Front camera | Optical axis along `y`, lens aimed at the wire midpoint, object plane at the wire centerline | Captures axial length plus vertical sag/bowing in `x-z` |
| Top camera | Optical axis along `z`, lens aimed at the wire midpoint, object plane at the wire centerline | Captures axial length plus lateral S-bowing in `x-y` |
| Front backlight | Opposite the front camera, behind the sample along `y` | Makes the wire a dark silhouette in the front view |
| Top backlight | Opposite the top camera, below/behind the sample along `z` as the fixture allows | Makes the wire a dark silhouette in the top view |
| Fiducial strip | Near the wire but electrically and chemically isolated | Defines scale, drift, endpoint registration, and focus/heat-haze QC |

For the 0.16X SilverTL-class baseline, set each lens so the nominal wire centerline is at the lens working distance. For the Edmund #56-675 reference lens this is **177 mm from the front of the lens to the object plane**, with a listed working-distance tolerance of ±3 mm. The vendor-listed depth of field is **±19.74 mm at f/10** under its 20% contrast at 20 lp/mm criterion, so the first rig should be aligned with the wire centered in that range and the iris near f/10 to f/16 if the 470 nm strobe has enough power.

If the wire expands into an S shape, it should remain usable as long as the deformed centerline stays inside both the field of view and the depth-of-field envelope:

- **Front view focus sensitivity:** lateral motion along `y` is defocus for the front camera. Keep `|y(x)| < ~10 mm` as the conservative high-accuracy envelope; `|y(x)|` approaching 20 mm may still be trackable but should be flagged as lower confidence.
- **Top view focus sensitivity:** vertical sag/bowing along `z` is defocus for the top camera. Keep `|z(x)| < ~10 mm` as the conservative high-accuracy envelope; `|z(x)|` approaching 20 mm should be quality-flagged.
- **S-shape reconstruction:** an S-shaped wire is exactly why the top/front geometry is useful. The front view measures `z(x)`, the top view measures `y(x)`, and the app reconstructs the 3D centerline `r(x) = [x, y(x), z(x)]` before integrating arc length.
- **Failure mode:** if the S shape pushes part of the wire outside the FOV or far enough out of focus that the silhouette edges broaden, the app should still attempt centerline tracking but mark width/diameter and arc-length uncertainty higher for those frames.

Practical alignment targets:

- Center the clip-to-clip gauge within the common FOV of both cameras, leaving at least 2-3 mm margin around the expected maximum bowing envelope.
- Keep the front and top optical axes as close to orthogonal as the fixture allows; exact 90 degree geometry is not mandatory if calibration captures the true transforms.
- Use a gauge pin or straight wire at the object plane to focus both lenses before heating, then record a defocus sweep by translating the pin ±5, ±10, and ±20 mm along each camera axis. Use that sweep to set the app's edge-sharpness QC threshold.
- Stop down only as much as needed for depth of field. f/10 is the reference point; f/16 may buy focus margin at the cost of strobe power, while f/22 may reduce edge sharpness from diffraction and low signal.

Hardware layout:

- Two matched 0.16X SilverTL-class telecentric lenses or equivalent, one per camera.
- Two 470 nm strobed backlights/line lights placed opposite the cameras. The wire should image as a high-contrast dark silhouette in each view.
- Rigid optical-table mounts for both cameras, both lights, and the clip fixture. Use kinematic or rail-mounted adjustments for yaw/pitch/roll, but lock all degrees of freedom before calibration.
- Fixed clips with non-glowing, off-sample fiducials near each endpoint. The fiducials define the gauge endpoints; do not rely on saturated clip metal as the endpoint marker.
- An alumina/sapphire/quartz fiducial strip or target next to the wire in the same optical volume. It should be electrically/chemically isolated from the active wire path.
- Heat shields, sacrificial quartz/sapphire windows, and purge/air-knife if heat shimmer, smoke, or deposition appears on the optics.
- Common trigger chain: timing box sends TTL to both cameras and both LED drivers, with OES/electrical data receiving either the same trigger or an accurately timestamped trigger marker.

Calibration targets:

- Use a flat dot-grid or ChArUco target for each individual camera view.
- Use a 3D calibration artifact or a target moved through several known depths to calibrate the top/front views into one metric coordinate system. Telecentric lenses are closer to affine/orthographic cameras than pinhole lenses, so the calibration model should explicitly validate scale and orthogonality over the working volume.
- Include a known-diameter wire or gauge pin and a known thermal-expansion standard for validation before Flash data.

## Video-To-3D Segmentation Pipeline

The primary reconstruction is silhouette-based, not DIC-based:

1. **Acquire synchronized frames.** Record raw 12-bit frames from top and front cameras, plus exposure/gain/filter/light metadata and trigger timestamps.
2. **Flat-field and background correct.** Record pre-run backlight-only frames. Correct each image for LED nonuniformity and subtract/ratio background to stabilize thresholding.
3. **Segment wire silhouette.** Use intensity thresholding in the narrow-band image to isolate the dark wire against the bright 470 nm backlight. Mask out clips, fiducials, and reactor features.
4. **Extract subpixel edges.** For every axial row/column along the wire, find the two silhouette edges and refine them with a subpixel edge method. OpenCV gives contour and gradient primitives, but robust subpixel edge extraction usually needs a custom Steger-style or gradient/centroid refinement.
5. **Compute 2D centerlines and widths.** In each view, centerline is the midpoint between the two subpixel edges; apparent width is the edge separation after calibration.
6. **Register to clip fiducials.** Detect the fixed endpoint fiducials and express the wire centerline in the gauge coordinate system. This removes camera drift and fixture motion.
7. **Fuse top/front views.** Use calibrated top/front camera transforms to combine the two projected centerlines into a 3D centerline `r(s)`. With orthogonal telecentric views, the first-order fusion is direct: front gives `x-z`, top gives `x-y`, and shared fiducials align `x`.
8. **Compute length and deformation metrics.** Calculate 3D arc length between endpoint fiducials, end-to-end distance, curvature/bowing, width/diameter versus axial coordinate, and local swelling/necking.
9. **Quality-control every frame.** Store segmentation confidence, edge contrast, saturation fraction, fiducial reprojection error, top/front centerline consistency, and estimated uncertainty. Reject frames where glow overwhelms the backlight or fiducials are lost.

For a circular wire, two orthogonal silhouette widths are enough to report apparent diameter and ellipticity assumptions. If the wire becomes strongly non-circular or twists, add a third oblique camera later. Cylinder geometry can be reconstructed from silhouettes with known camera geometry, but constrained cylinder/circle models are more robust than unconstrained quadric fits.

## Open-Source Software Architecture

- Keep the existing Flash camera app as the acquisition front end. Add a stereo session mode that stores: camera serials, lens/filter/illumination IDs, exposure/gain, trigger delay, calibration file hash, OES timestamp stream, current/voltage stream, and raw frames.
- Use **OpenCV** for ChArUco/dot-grid calibration, stereo calibration, rectification, fiducial tracking, segmentation, and triangulation.
- For wires, implement a dedicated **stereo wire metrology pipeline** before any DIC backend: detect left/right wire edges in each camera, extract subpixel centerlines, triangulate the 3D centerline, compute arc length between fixed clip fiducials, and estimate diameter/width versus axial coordinate from calibrated multi-view silhouettes.
- Use **DICe** only as a secondary open-source DIC backend for foil surfaces or wire cases with natural texture that survives Flash without perturbing the sample.
- Keep **OpenCorr** as the second backend to benchmark for foil/natural-texture cases; it supports 2D, stereo 3D, and volumetric DIC in C++ and is better suited to method development than a turnkey GUI-only stack.
- Use DuoDIC/MultiDIC only as MATLAB reference implementations or for cross-checking results, not as the production app backend.

## Balluffi / Defect-Density Path

- The Simmons-Balluffi logic requires comparing macroscopic expansion with microscopic lattice expansion. In the simple isotropic vacancy form, the vacancy concentration is commonly expressed as `N_v = 3[(Delta L/L0) - (Delta a/a0)]`; the method depends on simultaneous or otherwise well-registered specimen length and lattice-parameter measurements.
- For Flash, use video dilatometry to obtain `Delta L/L0` and in-situ XRD or a calibrated lattice-parameter/temperature model for `Delta a/a0`.
- Treat the first output as **excess macroscopic strain**, not automatically defect density, until temperature, lattice parameter, mechanical bowing, clamp motion, and possible plastic deformation are separated.

Useful first-order lookup table:

| Apparent defect fraction | Balluffi excess linear strain `c/3` | Extra length on 48 mm gauge | Extra diameter on 250 um wire | Total linear strain with ~0.9% Pt CTE |
|---:|---:|---:|---:|---:|
| 5 mol% | 1.67% | 0.80 mm | 4.2 um | 2.57% |
| 10 mol% | 3.33% | 1.60 mm | 8.3 um | 4.23% |
| 15 mol% | 5.00% | 2.40 mm | 12.5 um | 5.90% |
| 20 mol% | 6.67% | 3.20 mm | 16.7 um | 7.57% |
| 25 mol% | 8.33% | 4.00 mm | 20.8 um | 9.23% |
| 30 mol% | 10.00% | 4.80 mm | 25.0 um | 10.90% |

App calculation requirements:

- Compute measured macroscopic strain from the 3D model: `epsilon_macro = (L_3D(t) - L_0) / L_0`.
- Compute thermal strain from a selected material model: `epsilon_CTE = integral(alpha(T) dT)` or a constant-CTE approximation for calibration runs.
- If lattice data are available, use measured or modeled `epsilon_lattice = Delta a/a0`. If not, use `epsilon_CTE` as the first thermal-lattice estimate and label the result as apparent.
- Compute excess strain: `epsilon_excess = epsilon_macro - epsilon_lattice`.
- Compute apparent defect fraction: `c_app = 3 * epsilon_excess`.
- Export `epsilon_macro`, `epsilon_CTE`, `epsilon_lattice`, `epsilon_excess`, `c_app_mol_percent`, 3D arc length, end-to-end length, diameter/width, temperature, OES timestamp, and uncertainty flags in the session CSV/JSON.
- Display the Balluffi calculation as **apparent defect swelling** unless synchronized lattice-parameter data are present. Defect fractions above a few mol% are outside the dilute vacancy regime, so the app should warn when `c_app > 0.02`.

## Build Sequence

1. **Finish hardware inventory.** Confirm Allied Vision serial/model after VmbPy/Vimba X install; Basler `a2A2840-48umUV` serial `40775503` is already confirmed.
2. **Procure/verify optics.** Buy or quote a matched 0.16X SilverTL-class telecentric pair, 470 nm camera filters, ND filters, two 470 nm strobed backlights/line lights, and TTL LED drivers.
3. **Build top/front orthogonal rig.** Mount one camera front-view and one top-view with matching 0.16X telecentric optics; place 470 nm backlights opposite each camera; add fixed-clip fiducials and an isolated off-sample calibration/fiducial strip.
4. **Calibrate.** Calibrate each camera, then calibrate the shared top/front metric coordinate system with a dot-grid/ChArUco target and a moved-depth or 3D calibration artifact. Validate scale using gauge pins/known-diameter wire.
5. **Implement app stereo session.** Extend the Flash camera app for camera-pair selection, hardware trigger settings, light/filter metadata, calibration file loading, raw-frame export, OES/electrical timestamp registration, and session-level QC.
6. **Implement wire reconstruction.** Segment 470 nm silhouettes, extract subpixel edges, compute 2D widths/centerlines, align to clip fiducials, fuse top/front views into a 3D tube model, and export arc length, end-to-end length, bowing, and diameter/width.
7. **Validate on standards.** Run room-temperature gauge pins, a non-flash translated wire, and a Pt thermal expansion run. Confirm that axial CTE is measurable and quantify width noise.
8. **Add Balluffi panel.** Calculate `epsilon_macro`, `epsilon_CTE`, `epsilon_lattice` when available, `epsilon_excess`, and `c_app = 3 * epsilon_excess`, with warnings for non-dilute apparent defect fractions.
9. **Run Flash experiments.** Report geometry first: 3D length expansion, bowing, and width/diameter change. Report defect-density inference only as apparent unless paired lattice-parameter data exist.

## Immediate Default Choice

Build first. Use the existing Basler/Allied IMX487 cameras and Flash camera app, buy the 0.16X SilverTL-class telecentric pair or true-2/3-inch equivalent, use 470 nm strobed backlit silhouette imaging, and implement the custom OpenCV stereo tube reconstruction. Keep DICe/OpenCorr/MultiDIC as validation/reference tools, not the core wire pipeline.

The first purchasing decision should be **metrology optics and illumination**, not software: matched 0.16X telecentric lenses, matched 470 nm OD4+ bandpass filters, ND filters, two triggerable 470 nm backlights/line lights, calibration targets, and off-sample fiducials.
