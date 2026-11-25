# Self-hosted fonts

| File                             | Family                    | Weights kept | Licence                   | Upstream                                        |
| -------------------------------- | ------------------------- | ------------ | ------------------------- | ----------------------------------------------- |
| `inter-latin-var.woff2`          | Inter (variable)          | 400–700      | SIL Open Font License 1.1 | https://github.com/rsms/inter                   |
| `space-grotesk-latin-var.woff2`  | Space Grotesk (variable)  | 500–700      | SIL Open Font License 1.1 | https://github.com/floriankarsten/space-grotesk |
| `jetbrains-mono-latin-var.woff2` | JetBrains Mono (variable) | 400–600      | SIL Open Font License 1.1 | https://github.com/JetBrains/JetBrainsMono      |

Made by `tools/subset_fonts.py` from the Latin files Google Fonts serves (the same files
`next/font/google` used before Phase 6): weight axis limited to the range above, characters
limited to Basic Latin, Latin-1 Supplement and the few symbols the UI prints (– — ‘ ’ “ ” • … →
− ≤ ≥ ≈ ✓ and others listed in the script). Each family's OFL text is at its upstream repository above; keep these notes with the files.

To add a character the UI starts using, add it to `UNICODES` in the script and re-run it.
