**Krok 2: Zernio i klucz**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Zakładamy konto w Zernio, podpinamy do niego twój Instagram i zapisujemy tajny klucz w pliku na twoim komputerze.

## Po co

Zernio to usługa, która łączy się z twoim Instagramem (za twoją zgodą) i publikuje rolki o zaplanowanej godzinie. Program przygotowuje rolki i zleca Zernio ich publikację. Żeby Zernio wiedziało, że zlecenie przychodzi od ciebie, program używa klucza API: długiego, tajnego ciągu znaków, czegoś w rodzaju hasła dla programu. Kto ma ten klucz, może zlecać Zernio publikacje na twoim koncie. Dlatego klucz zostaje w jednym pliku na twoim komputerze i nigdy nie trafia do czatu.

## Co robisz Ty

1. Wejdź na stronę Zernio (zernio.com) i załóż konto albo zaloguj się. Zanim podepniesz konta, sprawdź aktualny cennik Zernio: od liczby podpiętych kont może zależeć opłata.
2. W panelu Zernio podłącz konto Instagram (przycisk w rodzaju „Connect” albo „Dodaj konto”). Otworzy się okno Instagrama z prośbą o zgodę. Zaloguj się tam sam(a) i zatwierdź. To okno należy do Instagrama: ja nie widzę ani nie wpisuję twoich haseł.
3. Podłącz tylko Instagram. Facebooka ani innych platform nie podłączaj, bo każde dodatkowe konto może liczyć się w Zernio osobno.
4. W panelu Zernio znajdź sekcję z kluczami API („API keys”) i utwórz nowy klucz („Generate”). Zostaw tę kartę otwartą, bo zaraz go skopiujesz. Klucz może być pokazany tylko raz. Nazwy w panelu mogą się trochę różnić od moich.
5. Gdy powiem, że plik jest otwarty (TextEdit na Macu, Notatnik w Windowsie), wklej klucz w tej samej linii tuż za znakiem `=`, bez spacji i bez cudzysłowów. Zapisz plik (Cmd+S albo Ctrl+S) i zamknij okno.
6. Nie wklejaj klucza do czatu. Wróć i napisz „gotowe”.

## Co robię ja

1. Uruchamiam komendę `klucz`: `bash trial.sh klucz` albo `.\trial.cmd klucz`. Program tworzy folder `dane` i w nim plik `dane/.env` z jedną linią `ZERNIO_API_KEY=` (tylko wtedy, gdy pliku jeszcze nie ma; na Macu z prawami tylko dla konta klienta) i otwiera go klientowi w edytorze. Istniejącego pliku nie nadpisuje i nie pokazuje jego treści.
2. Sam tego pliku nie tworzę, nie otwieram i nie edytuję: robi to tylko komenda `klucz`, a `.claude/settings.json` zabrania narzędziom do czytania i edycji plików dostępu do niego.
3. Czekam na „gotowe”. Nie czytam treści pliku (ani narzędziem do czytania plików, ani komendami `cat`, `type`, `Get-Content`, `grep`) i nie proszę o klucz.
4. Sprawdzam wyłącznie komendą `krok`: `bash trial.sh krok` albo `.\trial.cmd krok`.

## Jak sprawdzamy

`krok` pokazuje krok `zernio` jako gotowy, a w polu `szczegoly` stoi „Klucz Zernio jest w dane/.env.” Klucza nie pokazuję ani nie powtarzam. To, czy Zernio klucz przyjmie, sprawdzi się w następnym kroku komendą `konto`.

## Gdy nie wychodzi

- Klient wkleił klucz do czatu. Nie powtarzaj go i nigdzie nie zapisuj. Powiedz spokojnie, że klucz był w rozmowie, więc najlepiej utworzyć w Zernio nowy, usunąć stary i wkleić nowy do pliku.
- `krok` pisze „Brak klucza ZERNIO_API_KEY w dane/.env”. Plik nie został zapisany albo klucz stoi w złym miejscu. Uruchom `klucz` jeszcze raz (otworzy ten sam plik) i poproś klienta o sprawdzenie, czy linia zaczyna się od `ZERNIO_API_KEY=`, a zaraz po znaku `=` jest klucz. Niech opisze, co widzi, bez wklejania klucza. Nie czytaj pliku sam.
- Notatnik zapisał plik pod nazwą `.env.txt` (na Windowsie to częste), więc `krok` dalej pisze „Brak klucza”. Uruchom `klucz` jeszcze raz: gdy w `dane/.env` nie ma klucza, a w `dane/.env.txt` jest, program sam przeniesie klucz do `dane/.env` i napisze o tym (bez pokazywania klucza). Żadnego z tych plików nie czytam, nie przenoszę i nie usuwam sam. Potem sprawdzam `krok`.
- `klucz` pisze „Nie udało się otworzyć edytora”. Poproś klienta, żeby sam otworzył plik `.env` z folderu `dane` w edytorze tekstu (TextEdit, Notatnik), wkleił klucz za znakiem `=` i zapisał plik. To plik ukryty: na Macu Finder pokaże go po skrócie Cmd+Shift+kropka.
- Zernio nie pokazuje już klucza. Utwórz nowy.
- Zernio nie chce podłączyć Instagrama. Najczęściej to konto osobiste zamiast firmowego albo twórcy. Pomaga zmiana typu konta w ustawieniach Instagrama (patrz krok 0) i ponowna próba. Jeśli to nie pomaga, poproś o zrzut ekranu komunikatu i opisz problem opiekunowi.
