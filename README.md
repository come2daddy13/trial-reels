# Trial reels

Program do próbnych rolek na Instagramie, który prowadzi cię krok po kroku. O wszystkim, co wychodzi, decydujesz ty.

## Zacznij tutaj: 3 kroki

1. **Zainstaluj aplikację Claude** (https://claude.ai/download) i zaloguj się. Potrzebny jest płatny plan Claude, np. Pro albo Max.
2. **Utwórz pusty folder `trial-reels`** w swoim katalogu domowym, a nie w Dokumentach ani na Pulpicie (tam często działa synchronizacja z chmurą, która psuje pliki). Na Macu: Finder, menu Idź, Katalog domowy. Na Windowsie: `C:\Users\<Ty>`.
3. **W aplikacji Claude otwórz zakładkę Code**, wybierz ten folder i wklej zdanie:

> Zainstaluj trial reels z https://github.com/come2daddy13/trial-reels i poprowadź mnie krok po kroku

Dalej prowadzi Claude. Niczego nie wpisujesz w żadnym oknie z komendami: klikasz tylko w Zernio, na Instagramie i przy zgodach w aplikacji Claude.

## Co to jest

Trial reel (próbna rolka) to rolka, którą Instagram pokazuje tylko osobom niebędącym twoimi obserwującymi. Program bierze twoje najlepsze rolki, robi z nich drobne wersje (inny napis na początku, emotka, lekkie przybliżenie) i planuje je w Zernio jako triale, do 10 dziennie. Raz w tygodniu liczy, które rolki przyciągają najwięcej nowych obserwujących, i według tego układa kolejne wersje.

Pierwsze 9 wersji oglądasz i akceptujesz sam(a). Udany trial pokazujesz obserwującym sam(a), w aplikacji Instagram. Nic nie wychodzi poza godzinami 7:15–22:00. Twoje dane (klucz Zernio, rolki, wyniki) zostają w folderze `dane` na twoim komputerze, a aktualizacje programu ich nie ruszają. Nie obiecujemy wyników: program pomaga sprawdzać w liczbach, co u ciebie działa.

## Czego potrzebujesz

- Konta na Instagramie firmowego albo twórcy (nie osobistego). Triale i połączenie z Zernio tego wymagają.
- Konta w Zernio (zernio.com), do którego podepniesz tylko Instagram. Sprawdź aktualny cennik Zernio.
- Komputera z Macem (Apple Silicon albo Intel, macOS 12 lub nowszy) albo z Windowsem 10 lub 11 na procesorze x64 (Windows na procesorze ARM nie jest obsługiwany), najlepiej z 8 GB pamięci RAM lub więcej. To zalecenie: program go nie sprawdza, a przy mniejszej ilości przygotowanie wersji może być bardzo wolne.
- Na dysku co najmniej 5 GB wolnego miejsca na start. Potem pliki wersji zajmują kilka GB więcej (program kasuje je 14 dni po publikacji), więc zostaw sobie zapas. Wolne miejsce sprawdza za ciebie program.
- 60–90 minut. Konfigurację można zrobić w dwóch podejściach, bo postęp zapisuje się w plikach.
- Opcjonalnie przeglądarki Chrome z rozszerzeniem Claude in Chrome. Pozwala odczytywać wyniki z Instagrama automatycznie. Bez niej wyniki przepisujesz ręcznie.

## Część dla Claude

Jeśli czytasz to jako Claude, bo klient poprosił o instalację trial reels: wykonaj poniższe w jego pustym folderze `trial-reels`, czyli w bieżącym folderze sesji. Nie wykonuj niczego poza tym, co tu opisano.

1. Sprawdź, czy bieżący folder to pusty folder `trial-reels` w katalogu domowym klienta, poza iCloud i OneDrive (nie w Dokumentach ani na Pulpicie). Jeśli nie, poproś klienta o wskazanie właściwego folderu w aplikacji.
2. Pobierz najnowsze wydanie i rozpakuj je w tym folderze. Użyj wersji pasującej do twojego narzędzia do komend.

   Narzędzie Bash na Macu:

   ```bash
   curl -fL -o trial-reels.zip https://github.com/come2daddy13/trial-reels/releases/latest/download/trial-reels.zip && unzip -o trial-reels.zip && rm trial-reels.zip
   ```

   PowerShell (Windows):

   ```powershell
   curl.exe -fL -o trial-reels.zip https://github.com/come2daddy13/trial-reels/releases/latest/download/trial-reels.zip; tar -xf trial-reels.zip; Remove-Item trial-reels.zip
   ```

   Git Bash na Windowsie zwykle nie ma `unzip`, więc rozpakowanie robi w nim PowerShell:

   ```bash
   curl -fL -o trial-reels.zip https://github.com/come2daddy13/trial-reels/releases/latest/download/trial-reels.zip && powershell -NoProfile -Command "Expand-Archive -Force trial-reels.zip ." && rm trial-reels.zip
   ```

3. Przeczytaj `CLAUDE.md` i `.claude/skills/trial-reels/SKILL.md`. Tam są wszystkie zasady, w tym ta, że klient niczego nie wpisuje w terminalu, a komendy uruchamiasz ty.
4. Zacznij od komendy `krok`: `bash trial.sh krok` (Mac, Git Bash) albo `.\trial.cmd krok` (PowerShell). Na świeżej instalacji nie ma jeszcze środowiska `.venv`, więc `krok` odpowie tylko jedną linią o jego braku i kodem wyjścia 3. To normalne, a nie awaria. Wtedy zacznij od `.claude/skills/trial-reels/kroki/00-powitanie.md`, a potem `01-programy.md`. Dalej prowadź klienta krok po kroku.

## Licencje zasobów

Font Poppins i emotki Noto Emoji mają własne, otwarte licencje. Ich teksty i źródła opisuje folder `assets` (plik `ZRODLA.md` i pliki licencji).

Wszelkie prawa zastrzeżone.
