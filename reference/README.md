# Reference board

This folder is the visual source material for the mascot. The final widget uses a
cleaned, transparent cutout of the isolated chibi reference, embedded directly in
`assets/whale-chan.svg`, so the face, proportions, hair, and costume are kept
pixel-faithful to the community art instead of being approximated by vector shapes.

## Primary character art

| File | What it shows | Source |
| --- | --- | --- |
| [`isolated/neutral_standing_front_isolated.webp`](isolated/neutral_standing_front_isolated.webp) | The exact full-body chibi used as the base for the final mascot | [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan) · `skills/whalechan-image-character/assets/reference-images/semi-chibi/neutral_standing_front_isolated.webp` |
| [`isolated/whalechan-art-master.webp`](isolated/whalechan-art-master.webp) | Cleaned transparent master embedded in the SVG | Derived from the file above: connected-background removal, cream-fringe cleanup, floor-shadow removal, alpha decontamination |
| [`central-chibi-crop.webp`](central-chibi-crop.webp) | Waist-up chibi with the same face and maid details | Cropped from the expression sheet below |
| [`central-chibi-face.webp`](central-chibi-face.webp) | Face close-up used for eye/hair proportion checks | Cropped from the expression sheet below |

## Additional isolated poses

These are kept for character consistency checks and future expressions.

| File | Pose |
| --- | --- |
| [`isolated/0054_rice_identity_comic_rendered_isolated.webp`](isolated/0054_rice_identity_comic_rendered_isolated.webp) | Raised fist + giant rice bowl |
| [`isolated/0057_patting_full_belly_rendered_isolated.webp`](isolated/0057_patting_full_belly_rendered_isolated.webp) | Lying down, patting belly |
| [`isolated/01_gentle_wave.webp`](isolated/01_gentle_wave.webp) | Standard-form gentle wave |
| [`isolated/0015_data_still_in_brain_rendered_isolated.webp`](isolated/0015_data_still_in_brain_rendered_isolated.webp) | Semi-chibi standing |
| [`isolated/0019_literal_love_reply_rendered_isolated.webp`](isolated/0019_literal_love_reply_rendered_isolated.webp) | Super-deformed expression |
| [`isolated/0040_kicked_from_chair_rendered_isolated.webp`](isolated/0040_kicked_from_chair_rendered_isolated.webp) | Super-deformed action |
| [`isolated/0067_angry_you_are_silly_reply_rendered_isolated.webp`](isolated/0067_angry_you_are_silly_reply_rendered_isolated.webp) | Pouty chibi |

## Reference boards

| File | What it shows | Source |
| --- | --- | --- |
| [`deepseek-whale-maid-portrait.png`](deepseek-whale-maid-portrait.png) | Full-body maid outfit, gradient hair, tail, apron | [36Kr: "A whale girl has emerged from DeepSeek"](https://eu.36kr.com/en/p/3947452108789632) |
| [`whalechan-standard-portrait.webp`](whalechan-standard-portrait.webp) | Standard-form character portrait / palette | [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan) · `assets/readme/en/whalechan-standard-character-portrait.webp` |
| [`whalechan-expression-sheet.webp`](whalechan-expression-sheet.webp) | Chibi mood / expression guide | [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan) · `assets/readme/en/character-samples/whalechan-character-expression-guide-reference-sheet.webp` |
| [`whalechan-color-sheet.webp`](whalechan-color-sheet.webp) | Color and material reference | [Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan) · `assets/readme/en/character-samples/whalechan-character-color-material-reference-sheet.webp` |
| [`whalechan-readme-source.md`](whalechan-readme-source.md) | Saved copy of the design/profile notes | [Neko3000/deepseek-whalechan README](https://github.com/Neko3000/deepseek-whalechan) |

## Art pipeline

1. **Cut out** the character from the cream background using a border-connected
   matte, then remove disconnected cream pockets.
2. **Decontaminate** fringe pixels against the original background colour so the
   lineart does not carry a beige halo.
3. **Remove** the baked-in floor shadow so the widget can cast its own soft shadow.
4. **Preserve** the original face, eye gradients, hair shading, lace, and gold trim
   at source resolution.
5. **Embed** the cleaned WebP in the animated SVG and add the float, silhouette
   light sweep, bubbles, and sparkles around it.

The widget itself, drag physics, speech bubble, rice particles, and the demo page
are original code.

## Attribution / licensing

The character **Whale-chan / 鲸鱼娘** is a community fan creation, not an official
DeepSeek mascot. The reference asset library by
[Neko3000/deepseek-whalechan](https://github.com/Neko3000/deepseek-whalechan)
is shared under **CC BY-NC-SA 4.0**; its README notes that the original character
"Mingyue" by **Shangshan Wuxing** was released under the same license. The cleaned
master and its use in the mascot remain under those non-commercial, share-alike
terms.
