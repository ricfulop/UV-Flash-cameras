# 3D Wire Flash Dilatometer Vendor Quote Request

## Purpose

We are building a two-camera 3D wire dilatometer for Flash experiments. Please quote equivalent components or advise if your proposed alternative improves measurement accuracy for a 250 um wire and 48 mm gauge view under bright plasma/thermal emission.

## Application

- Sample: 250 um wire between fixed clips; secondary use case is 5 mm x 50 mm x 50 um foil.
- Measurement: 3D wire centerline arc length, end-to-end length, bowing/S-shape, and width/diameter change.
- Primary imaging mode: backlit 470 nm silhouette through narrow bandpass filters.
- Environment: bright Flash event with plasma/thermal emission; OES recorded separately from 200 nm to 1.7 um.
- Cameras in hand: Basler ace 2 X `a2A2840-48umUV` and Allied Vision Alvium 1800 U-812 UV or IMX487 equivalent.
- Sensor baseline: Sony IMX487, about 2840 x 2840 px, 2.74 um pixels, 2/3 inch format.

## Baseline Optics Request

Quote a matched pair of telecentric lenses equivalent to:

- Magnification: 0.16X.
- Working distance: about 177 mm.
- Object field of view target: about 48 mm across on a 2/3 inch IMX487-class sensor.
- Spectral operation: 470 nm visible blue baseline.
- Image circle: must support 2/3 inch format without unacceptable vignetting.
- Depth of field target: at least ±10 mm high-confidence envelope; ±20 mm useful tracking envelope preferred.

The Edmund Optics #56-675 0.16X SilverTL is the reference candidate, but it is listed for maximum 1/2 inch format. Please quote a true 2/3 inch equivalent if available.

## Illumination And Filter Request

Quote two matched illumination paths:

- 470 nm strobed backlight or line/bar light, one per camera view.
- TTL-triggerable LED driver or two-channel strobe controller.
- 470 nm camera bandpass filters, 10-25 nm FWHM preferred.
- OD4 minimum out-of-band blocking; OD5-OD6 preferred if available.
- ND filter options for alignment and Flash-on operation.
- Diffusers/backlight plates that do not fluoresce significantly under blue/near-UV illumination.
- Mechanical filter holders or lens-tube adapters compatible with the quoted lens/camera mounts.

## Geometry

- Front camera: horizontal view, measures `x-z` projection.
- Top camera: top view, measures `x-y` projection.
- Cameras should be orthogonal or near-orthogonal; exact geometry will be calibrated.
- Backlights should sit opposite each camera so the wire is a dark silhouette.

## Required Quote Information

Please include:

- Lens model, magnification, working distance, field of view on 2/3 inch IMX487, and image circle.
- Depth of field at a practical aperture near f/10 to f/16.
- 470 nm transmission or coating data.
- Expected distortion/telecentricity.
- Mechanical mount, weight, and adapter needs for C-mount cameras.
- Lead time and price for a matched pair.
- Recommended 470 nm filter and illumination stack.
- Any alternate lens that improves width resolution while preserving at least a 48 mm gauge view.

## Optional Upgrade Quote

Also quote a full-frame high-resolution option for comparison:

- Camera class: ASI6200 / Sony IMX455 equivalent, 9576 x 6388 px, 3.76 um pixels, 36 mm x 24 mm full frame.
- Telecentric magnification target: 0.75X for about 48 mm horizontal FOV.
- Need a full-frame image circle around 43.3 mm.
- Use case: slower or event-integrated high-resolution measurements, not necessarily high-speed Flash onset.

