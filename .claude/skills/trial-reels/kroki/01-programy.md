**Krok 1: Programy**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Instalujemy na twoim komputerze potrzebne programy (Python i dodatki) i sprawdzamy, czy komputer jest gotowy.

## Po co

Program do trial reels jest napisany w Pythonie. Montuje wideo i rozpoznaje mowę z twoich rolek. Instalacja nie wymaga hasła administratora ani Homebrew. Większość zostaje w folderze `trial-reels` (środowisko programu w ukrytym folderze `.venv`), ale kilka rzeczy ląduje poza nim, w twoim katalogu użytkownika. To normalne i nie psuje niczego w komputerze, a zanim cokolwiek zainstaluję, powiem ci, co to jest.

## Co robisz Ty

1. Wysłuchaj, co zostaje poza folderem `trial-reels` (powiem to, zanim zainstaluję cokolwiek):
   - program `uv`, który instaluje Pythona (w `~/.local/bin`),
   - sam Python 3.12 (w katalogu danych programu `uv`),
   - jedna linia dopisana przez instalator `uv` do plików startowych powłoki (na Macu zwykle `~/.zshrc` i `~/.profile`; na Windowsie instalator dodaje swój folder do ścieżki użytkownika),
   - w kroku 5 model rozpoznawania mowy: ok. 1,6–1,8 GB w `~/.cache/huggingface` (na Windowsie z polskimi literami w nazwie użytkownika w `C:\Users\Public\trial-reels-model`, bo przy takiej nazwie biblioteka rozpoznawania mowy mogłaby nie otworzyć modelu).

   Wszystko da się potem usunąć, a jak, opisuję na końcu tego kroku. Napisz, że się zgadzasz.
2. Nic nie instalujesz sam(a). Obserwuj ekran: aplikacja Claude będzie prosić o zgodę na kolejne komendy. Przed każdą powiem, co robi, a ty klikasz „zezwól”.
3. Poczekaj. To potrwa od kilku do kilkunastu minut, bo pobierają się Python i dodatki (kilkaset MB). Komputer może chodzić trochę wolniej.
4. Jeśli system albo antywirus zapyta o zgodę (zwykle przy pierwszym uruchomieniu instalatora), potwierdź.

## Co robię ja

1. Zanim cokolwiek zainstaluję, mówię klientowi, co zostaje poza folderem `trial-reels` (punkt 1 z „Co robisz Ty”), i czekam na jego zgodę. Potem sprawdzam, czy jest `uv` (narzędzie do zarządzania Pythonem): `uv --version`. Gdy powłoka go nie widzi (kod 127, „command not found”), sprawdzam jeszcze pełną ścieżką, bo `uv` z wcześniejszej instalacji leży w katalogu użytkownika, ale nowa rozmowa nie ma go na ścieżce powłoki: Mac `~/.local/bin/uv --version`, Windows `%USERPROFILE%\.local\bin\uv.exe --version`. Jeśli któraś z tych komend działa, pomijam instalację `uv` i w kolejnych punktach wołam go w tej samej postaci, która zadziałała.
2. Jeśli `uv` nie ma ani na ścieżce powłoki, ani w katalogu użytkownika, instaluję je oficjalnym instalatorem. Zapisuje się w katalogu użytkownika i nie wymaga hasła administratora. Mówię klientowi, co to za komenda, zanim aplikacja o nią zapyta.

   Mac:

   ```
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Windows (działa w PowerShellu i w Git Bash):

   ```
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Tuż po instalacji `uv` może nie być jeszcze na ścieżce w tej sesji. Wołam go wtedy pełną ścieżką: Mac `~/.local/bin/uv`, Windows `%USERPROFILE%\.local\bin\uv.exe` (starsze wersje instalatora używały `~/.cargo/bin`).
3. Tworzę środowisko programu w folderze klienta. Python 3.12 `uv` pobierze sam, jeśli trzeba: `uv venv --python 3.12 .venv` (gdy sam `uv` nie działa, na Macu `~/.local/bin/uv venv --python 3.12 .venv`)
4. Instaluję pakiety: `uv pip install --python .venv -r requirements.txt` (też w postaci, która działa: np. `~/.local/bin/uv pip install --python .venv -r requirements.txt`). Uruchamiam w tle, bo może trwać kilka minut.
5. Uruchamiam `doktor`: `bash trial.sh doktor` albo `.\trial.cmd doktor`.
6. Jeśli `krok` pokazuje jako następny `powitanie` (na świeżej instalacji nie dało się go zapisać przed instalacją), zapisuję go teraz: `bash trial.sh krok --gotowe powitanie` albo `.\trial.cmd krok --gotowe powitanie`.

## Jak sprawdzamy

Komenda `doktor` wypisuje po jednej linii z ✓ na każdą kontrolę (ostatnia to „Strefa czasowa”) i kończy się zdaniem „Wszystko gra: komputer jest gotowy.” Potem uruchamiam `krok`: krok `programy` jest gotowy („Komputer jest gotowy (kontroli doktora: N).”, gdzie N to liczba kontroli). Mówię klientowi, co się udało.

## Gdy nie wychodzi

- Instalator `uv` nie działa (brak internetu, komputer firmowy, antywirus). Sprawdź internet. Na komputerze firmowym instalacja może wymagać zgody działu IT. Jeśli to nie pomaga, opisz problem opiekunowi.
- Tuż po instalacji (albo w nowej rozmowie) `uv` nie jest znalezione. Wołaj go pełną ścieżką (punkty 1 i 2). Jeśli nadal nie działa, poproś klienta o zamknięcie i ponowne otwarcie aplikacji Claude w tym folderze. Postęp jest w plikach.
- `doktor` zgłasza ✗. Czytaj, który punkt. Najczęstsze:
  - „Pakiety Pythona” albo „ffmpeg z kodekiem H.264”: powtórz punkt 4 i uruchom `doktor` jeszcze raz. To także sposób na naprawę pakietów po aktualizacji.
  - „Wolne miejsce”: potrzeba co najmniej 5 GB (sam model rozpoznawania mowy ma ok. 1,6 GB, a paczka wersji na tydzień to kolejne ok. 1,3 GB). Doktor sprawdza to za każdym razem, bo przy 10 wersjach dziennie pliki wersji z czasem zajmują kilka GB (program kasuje je 14 dni po publikacji, a komenda `sprawdz` sprząta te, które są już po tym terminie). Poproś o zwolnienie miejsca i uruchom `doktor` ponownie.
  - „Strefa czasowa”: w `dane/config.json` pole `timezone` ma nazwę, której komputer nie zna. `doktor` pisze wtedy: „Nieznana strefa czasowa „X” w dane/config.json. Otwórz ten plik i w polu timezone wpisz nazwę w formie Europe/Warsaw albo usuń z pliku wiersz timezone.” Popraw plik za zgodą klienta. Dopóki strefa jest zła, `krok` pokazuje krok `programy` jako niegotowy („Do poprawienia: Strefa czasowa…”), a poza `wersja`, `doktor`, `krok` i `aktualizuj` inne komendy kończą się kodem 2 i tą samą jedną linią.
  - „Ustawienia (dane/config.json)”: plik ustawień jest uszkodzony (brakujący przecinek, zły cudzysłów albo nawias, zły układ, kodowanie inne niż UTF-8). `doktor` pisze, w której linii i kolumnie jest błąd. Popraw plik za zgodą klienta (albo, też za zgodą, usuń go: program wróci do ustawień domyślnych, a konto wybierzesz jeszcze raz komendą `konto`). Dopóki plik jest zły, działają tylko `wersja`, `doktor`, `krok` i `aktualizuj`, a pozostałe komendy kończą się kodem 1 i jedną linią o pliku.
  - „Folder poza iCloud i OneDrive”: folder leży w miejscu synchronizowanym z chmurą, co psuje pliki i spowalnia pracę. Poproś klienta o przeniesienie całego folderu `trial-reels` do katalogu domowego (Mac: Finder, Idź, Katalog domowy. Windows: `C:\Users\<ty>`) i o ponowne otwarcie go w aplikacji Claude (zakładka Code). `.venv` po przeniesieniu robię od nowa, bo jest przywiązany do miejsca: usuwam go (to tylko zainstalowane programy, nic twojego) i powtarzam punkty 3 i 4.
  - „Zapis w folderze dane”: folder jest tylko do odczytu albo zablokowany. Przenieś go do katalogu domowego.
- Pobieranie pakietów trwa bardzo długo albo się przerywa. Uruchom punkt 4 jeszcze raz. To, co już pobrane, zostaje.
- Klient pyta, jak to wszystko usunąć z komputera (albo chce odzyskać miejsce). Niczego z tego nie robisz bez jego zgody, a zaplanowane posty w Zernio klient usuwa osobno, w panelu Zernio. Po kolei: (1) folder `trial-reels` (jest w nim `.venv` i dane klienta, więc zapytaj, czy dane mają zostać); (2) model rozpoznawania mowy, czyli folder `~/.cache/huggingface` (Windows: `%USERPROFILE%\.cache\huggingface`, a przy polskich literach w nazwie użytkownika `C:\Users\Public\trial-reels-model`; jeśli klient używa innych programów z modelami, zapytaj, czy usunąć folder w całości); (3) Python i pamięć podręczna `uv`: foldery, które podają komendy `uv python dir` i `uv cache dir`; (4) program `uv`: pliki `uv` i `uvx` w `~/.local/bin` (Windows: `%USERPROFILE%\.local\bin`); (5) dopisek instalatora: linia `. "$HOME/.local/bin/env"` w plikach `~/.zshrc` i `~/.profile` (Windows: wpis w zmiennej PATH użytkownika, który klient usuwa sam w ustawieniach „Edytuj zmienne środowiskowe dla konta”).
