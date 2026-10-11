# shuai wordmark

The geometric lowercase **shuai** wordmark has a red **i** dot and an underline beneath **ai**.

- Light artwork: `../assets/brand/shuai-wordmark.png`, black letters on white.
- Dark artwork: `../assets/brand/shuai-wordmark-dark.png`, white letters on black.
- Both assets are 1774 × 887 pixels. Keep the red dot in both themes; the palette reference is `#B73832`.
- Preserve the proportions, letter spacing, and underline. The CSS viewport hides the image's extra padding.
- Use `mix-blend-mode: multiply` for the light artwork and `screen` for the dark artwork. Switch assets instead of inverting the image.
- Keep the mark in the page header. Do not overlay it onto the source video, subtitle previews, or exported video.
- Bundle both artworks inside the installable Skill so the editor works without external asset directories.
