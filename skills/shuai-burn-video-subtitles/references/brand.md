# shuai wordmark

Approved on 2026-10-11: option 01, the geometric lowercase **shuai** wordmark with the underline beneath **ai** only.

- Current artwork: `../assets/brand/shuai-wordmark-ai.png`, 1774 × 887 pixels, edited with imagegen to shorten only the underline. The original **uai** version is retained as `../assets/brand/shuai-wordmark.png`.
- Use the complete wordmark at the top-left of the review page. Preserve its proportions; the CSS viewport hides the source image's extra white padding.
- Light theme: black artwork with `mix-blend-mode: multiply`. Dark theme: CSS inversion with `mix-blend-mode: screen`.
- The current underline starts beneath **a** and ends beneath **i**, emphasizing the **ai** suffix. Preserve its thickness and vertical position; do not extend it beneath **u**.
- Keep the mark in the page header. Do not overlay it onto the source video, subtitle previews, or exported video.
- The asset lives inside the installable Skill so future installations carry it with the editor. Do not depend on the exploratory gallery or a personal generated-images directory.
- The shared brand foundation is `brand/shuai/` in the parent agent-skills workspace. about-me carries the same bundle under `public/brand/shuai/`. Keep artwork copies byte-identical when updating them.
