# Źródła zasobów

Font i emotki z tego folderu pochodzą z publicznych repozytoriów, przypiętych do konkretnych commitów.
Leżą w paczce, więc program niczego nie pobiera w czasie pracy ani nie sięga po fonty z systemu.
Dzięki temu hook na rolce wygląda tak samo na Macu i na Windowsie.

## Font: Poppins Bold

- Repozytorium: https://github.com/google/fonts
- Commit: `7af0d90b4d532ffa4b041937b560c6df4e7b1e95` (2026-11-16)
- Pliki w repozytorium: `ofl/poppins/Poppins-Bold.ttf` i `ofl/poppins/OFL.txt`
- Adres pliku fontu: https://raw.githubusercontent.com/google/fonts/7af0d90b4d532ffa4b041937b560c6df4e7b1e95/ofl/poppins/Poppins-Bold.ttf
- Zapisane tutaj jako: `fonts/Poppins-Bold.ttf` i `fonts/OFL.txt`
- Licencja: SIL Open Font License 1.1, tekst w `fonts/OFL.txt` (prawa autorskie: The Poppins Project Authors)

## Emotki: Noto Emoji, PNG 128 px

- Repozytorium: https://github.com/googlefonts/noto-emoji
- Commit: `99701e07d3d1fe1bdbcdb14964547f0fd592966f` (2026-10-26)
- Pliki w repozytorium: `2D/png/128/emoji_u<kod>.png` (30 plików) i `LICENSE`
- Adres pliku: https://raw.githubusercontent.com/googlefonts/noto-emoji/99701e07d3d1fe1bdbcdb14964547f0fd592966f/2D/png/128/emoji_u1f525.png
  (tu dla 🔥, dla innych zmienia się tylko kod)
- Zapisane tutaj jako: `emoji/<kod>.png`, `emoji/LICENSE` i `emoji/LICENSE-APACHE-2.0`
- Nazwa pliku to kody szesnastkowe znaków złączone znakiem „_”, bez fe0f: `1f525.png` to 🔥, `2764.png` to ❤.
  W repozytorium źródłowym ten sam plik nazywa się `emoji_u1f525.png`.
- Komplet (30): 🔥 1f525, 👀 1f440, 🤯 1f92f, ⚡ 26a1, ✅ 2705, 🎯 1f3af, 💡 1f4a1, 🚀 1f680, 📈 1f4c8,
  💰 1f4b0, ⏰ 23f0, 📌 1f4cc, 👇 1f447, 👉 1f449, 🙌 1f64c, 💪 1f4aa, 😮 1f62e, 😳 1f633, 🤔 1f914,
  😅 1f605, 😎 1f60e, 🧠 1f9e0, ❤ 2764, ⭐ 2b50, 🏆 1f3c6, 📱 1f4f1, 💬 1f4ac, 🛑 1f6d1, ❌ 274c, ✨ 2728.
- Nowa emotka: pobierz `2D/png/128/emoji_u<kod>.png` z tego samego commita i zapisz jako `emoji/<kod>.png`.
  Program bierze do hooków wszystkie pliki PNG z tego folderu.

### Licencje emotek

W przypiętym commicie plik `LICENSE` w katalogu głównym repozytorium to SIL Open Font License 1.1
(autorzy zmienili go z Apache 2.0 na OFL 2024-07-29). README tego samego commita nadal pisze, że obrazy
są na licencji Apache 2.0. Żeby nie zostawiać wątpliwości, dołączamy oba teksty:

- `emoji/LICENSE`: SIL Open Font License 1.1, plik z przypiętego commita, bez zmian.
- `emoji/LICENSE-APACHE-2.0`: Apache License 2.0, plik `LICENSE` z commita
  `41e31b110b4eb929dffb410264694a06205b7ad7` (2024-02-15), tuż przed zmianą na OFL. Bez zmian.

Obie licencje pozwalają dołączać te pliki do własnego oprogramowania i rozpowszechniać je, pod warunkiem
zachowania informacji o prawach autorskich i tekstu licencji.

## Jak sprawdzono pliki

Każdy plik porównano ze skrótem blobu git z drzewa przypiętego commita. Każdy PNG ma 128×128 pikseli,
a font otwiera się w Pillow i ma wszystkie polskie litery.
