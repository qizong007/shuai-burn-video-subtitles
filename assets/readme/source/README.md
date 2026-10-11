# README hero source

`hero-layout.svg` composes the existing monochrome illustration, the compact workbench UI, and the approved shuai logo. `hero-wordmark.png` is a byte-identical copy of the Skill's `assets/brand/shuai-wordmark-ai.png`.

From the repository root, export the 1200 × 440 PNG used by README:

```bash
rsvg-convert -o assets/readme/hero.png assets/readme/source/hero-layout.svg
```

Keep the PNG as the published image so GitHub does not need to resolve image references inside the SVG. No new image generation was used for this composition.
