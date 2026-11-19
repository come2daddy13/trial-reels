---
name: trial-reels
description: Trial reels (próbne rolki) na Instagramie klienta, czyli konfiguracja krok po kroku, tygodniowa paczka wersji planowana w Zernio, wyniki i raport oraz aktualizacja programu. Używaj, gdy klient pisze o trial reels, próbnych rolkach, konfiguracji, paczce na tydzień, wersjach rolek, hookach, wynikach, raporcie lub aktualizacji, a także w zadaniu tygodniowym.
---

# Trial reels

Ten skill prowadzi klienta przez program do próbnych rolek: najpierw konfiguracja krok po kroku, potem co tydzień paczka wersji planowana w Zernio. Tu są wszystkie zasady. Szczegóły każdego kroku leżą w `kroki/`, uzasadnienia metody w `DLACZEGO.md`, pułapki w `PULAPKI.md` (wszystkie obok tego pliku).

W tych tekstach „komenda `krok`” znaczy: `bash trial.sh krok` (Mac, Git Bash) albo `.\trial.cmd krok` (PowerShell). To samo dotyczy każdej innej komendy.

## Zasady stałe

1. **Nic poza oknem publikacji.** Okno to 7:15–22:00 czasu klienta (`day_window` w `dane/config.json`). Program odmawia terminów poza oknem. Nie omijaj tego i nie planuj niczego ręcznie w Zernio na noc. Okno zmieniasz tylko na wyraźną prośbę klienta.
2. **Triale tylko jako MANUAL.** Trial widzą wyłącznie osoby, które klienta nie obserwują. Do obserwujących puszcza go klient sam, w aplikacji Instagram. Nie włączaj automatycznego przepuszczania.
3. **Pierwsze 9 wersji akceptuje klient.** Komendę `akceptuj` uruchamiasz dopiero po tym, jak klient obejrzał podgląd i wyraźnie napisał „akceptuję” (wszystkie wersje albo wskazane numery TR-…). Komendę `zaplanuj` uruchamiasz dopiero po jego osobnym „tak” przy pokazanych terminach. Zdanie, którym program kończy `akceptuj` („Następny krok to zaplanuj, ale dopiero po wyraźnej zgodzie klienta na pokazane terminy …”), wskazuje tylko kolejny krok: to nie zgoda na planowanie. Nie akceptujesz i nie planujesz za niego. Prawdziwa `paczka` i tak odmówi, dopóki pierwsze wersje nie trafią do Zernio, a potem także dopóki któraś z pierwszych wersji czeka na decyzję klienta (zaakceptowanie albo odrzucenie).
4. **Nigdy nie czytaj ani nie wypisuj `dane/.env`.** Nie używaj do niego narzędzia do czytania plików ani komend w rodzaju `cat`, `type`, `Get-Content` czy `grep`, nie kopiuj go i nie pokazuj w wynikach komend (także przez `env` ani nagłówki żądań). Plik tworzy i otwiera klientowi w edytorze komenda `klucz` (ona też przenosi klucz, gdy Notatnik zapisał go jako `dane/.env.txt`, patrz `kroki/02-zernio.md`). Sam tego pliku nie tworzysz, nie otwierasz, nie edytujesz i nie przenosisz, a narzędzia do czytania i edycji plików mają do niego zakaz w `.claude/settings.json`. To, czy klucz jest, sprawdzasz wyłącznie komendą `krok`. Klucz nigdy nie idzie do czatu: klient wkleja go do pliku w edytorze.
5. **Nie loguj się za klienta i nie proś o hasła.** Ani do Zernio, ani do Instagrama, ani do poczty. Gdy strona prosi o logowanie, zatrzymaj się i poproś klienta, żeby zalogował się sam, w swojej przeglądarce. Haseł nie przyjmuj, także gdy klient chce je podać.
6. **Aktualizacja tylko po „tak” klienta** (patrz „Aktualizacja”).
7. **Bez obietnic wyników.** Nie wiadomo z góry, ile obserwujących przyniosą triale. Mów: „sprawdzimy to w liczbach”.

## Jak zaczynasz każdą rozmowę

1. Sprawdź, czy istnieje `.venv` (Mac: `.venv/bin/python`, Windows: `.venv\Scripts\python.exe`). Jeśli nie, programy nie są jeszcze zainstalowane (komenda `krok` odpowiedziałaby tylko linią o braku `.venv` i kodem 3): pomiń ją i zacznij od `kroki/00-powitanie.md`, potem `kroki/01-programy.md`.
2. Uruchom komendę `krok`. Zwraca JSON: `kroki` (lista z polami `id`, `tytul`, `gotowy`, `szczegoly`), `nastepny` (id pierwszego niegotowego kroku albo `null`) i `alerty` (lista zdań). Stan wynika z plików w `dane/`, a nie z pamięci rozmowy, więc działa po przerwie i w nowej rozmowie. Pole `szczegoly` to jedno zdanie o tym, co jest i czego brakuje.
3. Gdy `nastepny` nie jest `null`, przeczytaj plik tego kroku (tabela niżej) i prowadź klienta: jeden krok naraz.
4. Gdy `nastepny` jest `null`, kreator jest skończony. Zapytaj klienta, w czym pomóc (paczka, wyniki, raport, nowa rolka w puli, aktualizacja).
5. Gdy są `alerty`, patrz „Alerty z komendy krok”.
6. Postęp podaj jednym zdaniem („Mamy za sobą 4 z 12 kroków”). Nie wklejaj klientowi JSON-a.

| Nr | id | Plik | Krok jest gotowy, gdy |
|---|---|---|---|
| 0 | `powitanie` | `kroki/00-powitanie.md` | zapis `krok --gotowe powitanie` |
| 1 | `programy` | `kroki/01-programy.md` | `doktor` nie zgłasza problemów (`krok` sprawdza to sam) |
| 2 | `zernio` | `kroki/02-zernio.md` | w `dane/.env` jest klucz |
| 3 | `konto` | `kroki/03-konto.md` | w `dane/config.json` jest konto Instagrama |
| 4 | `zwyciezcy` | `kroki/04-zwyciezcy.md` | w puli jest co najmniej 1 aktywna rolka |
| 5 | `pliki` | `kroki/05-pliki.md` | każda aktywna rolka ma plik w `dane/src/` i transkrypcję |
| 6 | `ustawienia` | `kroki/06-ustawienia.md` | każda aktywna rolka ma `ustawienia_ok: true` |
| 7 | `hooki` | `kroki/07-hooki.md` | każda aktywna rolka ma `hooki_ok: true` i `sprawdz-pule` nie zgłasza problemów |
| 8 | `pierwsze` | `kroki/08-pierwsze.md` | co najmniej 1 wersja jest zaplanowana albo opublikowana |
| 9 | `pomiar` | `kroki/09-pomiar.md` | zapis `krok --gotowe pomiar --wartosc chrome` albo `reczny` |
| 10 | `tydzien` | `kroki/10-tydzien.md` | zapis `krok --gotowe tydzien` |
| 11 | `codziennie` | `kroki/11-codziennie.md` | zapis `krok --gotowe codziennie` |

Numery to te same, które program podaje w komunikatach (np. „Najpierw krok 8”). Zapisem (`krok --gotowe ID`, opcjonalnie z `--wartosc W`) oznaczasz tylko cztery kroki: `powitanie`, `pomiar`, `tydzien`, `codziennie`. Pozostałe `krok` sprawdza sam z plików, więc wystarczy uruchomić `krok` po wykonaniu kroku. Gdy krok liczony z plików nie chce być „gotowy”, popraw przyczynę (pole `szczegoly` ją podaje), a nie zapis. Próba zapisu takiego kroku niczego nie zmieni: program odpowie jedną linią (kod wyjścia 0) „Nic nie zapisałem: krok „…” sprawdzam sam, z plików w folderze dane (albo doktorem), więc ręczny zapis niczego by nie zmienił. Ręcznie oznacza się tylko kroki: powitanie, pomiar, tydzien, codziennie.”

## Powłoka i komendy

- Narzędzie Bash (Mac, Git Bash na Windowsie): `bash trial.sh <komenda>`.
- Narzędzie PowerShell (Windows): `.\trial.cmd <komenda>`.

Rozpoznaj powłokę po narzędziu, którego używasz do komend. Nie mieszaj postaci: w PowerShellu `bash trial.sh` może nie istnieć, a w Bashu `.\trial.cmd` nie ruszy.

- Wołaj komendy dokładnie w tej postaci, z folderu klienta. Inne postaci nie mają zgody w `.claude/settings.json`.
- W PowerShellu argumenty komend programu (plik `trial.cmd`) czyta jeszcze raz cmd.exe, dla którego znaki & | ^ < > % i cudzysłów prosty (") coś znaczą. Nie podawaj ich w argumentach komend: teksty z nimi (hooki, podpisy) zapisujesz w plikach w `dane/`, hook na klatce pokazujesz opcją `--hook-id`, powód odrzucenia (`--powod`) piszesz bez nich, a zamiast adresu rolki podajesz sam kod.
- Kody wyjścia: 0 to w porządku, 1 to problem do naprawienia (jedna linia po polsku) albo część wersji się nie udała, 2 to zła komenda (błąd w nazwie albo opcji, komunikat po angielsku z „usage” albo „invalid choice”) albo zła strefa czasowa w `dane/config.json` (jedna linia po polsku; `wersja`, `doktor`, `krok` i `aktualizuj` działają wtedy mimo to, a `doktor` pokaże, co poprawić; uszkodzony plik `dane/config.json` kończy pozostałe komendy kodem 1 i jedną linią po polsku, a te cztery też wtedy działają), 3 to brak środowiska `.venv`, czyli najpierw krok 1 (`kroki/01-programy.md`), 130 to przerwanie.
- Komunikat błędu to zwykle jedna linia po polsku. Przekaż jego sens własnymi słowami i zaproponuj następny ruch. Długi ślad błędu (tekst z „Traceback”) to błąd w programie: opisz go klientowi dwoma zdaniami i przygotuj opis problemu (na dole).
- Długie komendy (`pierwsze`, `paczka`, `pobierz`, `transkrybuj`, instalacja pakietów) mogą trwać dłużej niż limit jednej komendy (domyślnie 2 minuty, najwyżej 10). Uruchamiaj je w tle, jeśli narzędzie to umożliwia (opcja run_in_background narzędzia do komend), poczekaj na powiadomienie o ich końcu i nie sprawdzaj ich wyniku w pętli ani co chwilę. Gdy się przerwą albo skończą błędem, uruchom tę samą komendę jeszcze raz: pomija to, co już zrobione. Dotyczy to też zadania tygodniowego: `paczka` idzie w tle, a `raport` i podsumowanie dopiero po jej końcu (patrz „Cykl tygodniowy”).
- Gdy działa `paczka` albo `pierwsze`, komendy zapisujące stan (`akceptuj`, `odrzuc`, `zaplanuj`, `sprawdz`, `zapisz-wynik`, `hamulec`) czekają na jej koniec. `status`, `podglad`, `raport` i `do-odczytu` możesz uruchamiać zawsze.
- Zgody: wejścia `bash trial.sh …` i `.\trial.cmd …` są zezwolone w `.claude/settings.json`, poza `aktualizuj --tak`, które zawsze pyta. Ten sam plik zabrania narzędziom do czytania i edycji plików dostępu do `dane/.env` i `dane/.env.txt`. O inne komendy (instalacja `uv`, `open`, `Start-Process`) aplikacja zapyta. Przed każdą nową komendą powiedz klientowi, co robi.
- Godziny podawaj klientowi w jego czasie (strefa z `dane/config.json`, domyślnie Europe/Warsaw).

## Mapa komend

Każdą komendę wołasz jako `bash trial.sh <komenda>` albo `.\trial.cmd <komenda>`. Poniżej nazwy z najważniejszymi opcjami.

| Komenda | Co robi | Ważne |
|---|---|---|
| `krok` | Pokazuje stan 12 kroków, następny krok i alerty (JSON). Zawsze od niej zaczynasz. | `krok --gotowe ID` zapisuje tylko kroki powitanie, pomiar, tydzien i codziennie, a `--wartosc W` dodaje wartość (np. tryb pomiaru). |
| `wersja` | Numer wersji programu. | Do opisu problemu. |
| `doktor` | Kontrole komputera, po jednej linii na każdą kontrolę: Python, pakiety, ffmpeg z H.264, font, emotki, zapis w `dane/`, co najmniej 5 GB wolnego miejsca, folder poza iCloud i OneDrive, ustawienia (plik `dane/config.json` da się wczytać), strefa czasowa z `dane/config.json`. | Kod 1, gdy coś jest do poprawienia. Działa też przy złej strefie czasowej i przy uszkodzonym pliku ustawień (wiersz „Ustawienia (dane/config.json)”). |
| `klucz` | Tworzy `dane/.env` z jedną linią `ZERNIO_API_KEY=` (tylko gdy pliku nie ma; na Macu z prawami 600, czyli tylko dla konta klienta) i otwiera go klientowi w edytorze (TextEdit, Notatnik). Gdy Notatnik zapisał klucz jako `dane/.env.txt`, a w `dane/.env` klucza nie ma, przenosi go do `dane/.env`. | Treści pliku nigdy nie pokazuje: mówi najwyżej, że klucz już jest. Krok 2. |
| `konto` | Wybiera konto Instagrama z Zernio, zapisuje je i robi test odczytu rolek. | `konto --nick NICK`, gdy kont jest kilka. |
| `kandydaci` | Lista do 25 rolek wideo z największą liczbą wyświetleń (ostatnie 12 miesięcy, starsze niż 7 dni, bez reklam i triali). Zapis w `dane/kandydaci.json`. | Opcje `--miesiace N` i `--ile N`. |
| `js-odczyt` | Wypisuje skrypt do odczytu panelu statystyk Instagrama w Chrome. | Skrypt tylko czyta tekst strony. |
| `wynik-kandydata` | Zapisuje odczyt z panelu (wyświetlenia i obserwujący) przy kandydacie. | `wynik-kandydata KOD --wyswietlenia "12,3 tys." --obserwujacy 9` |
| `pula` | Bez argumentów pokazuje pulę. Z kodami dodaje kandydatów. `--auto N` dopełnia pulę do N aktywnych rolek (bez liczby: 12), według obserwujących, a bez odczytów według wyświetleń. | Kody podawaj przed `--auto`. `--auto` bierze też rolki wykreślone przez klienta, więc gdy cokolwiek wykreślił, podawaj kody wprost. |
| `pobierz` | Ściąga pliki aktywnych rolek z Zernio do `dane/src/`. | Rolka bez pliku w Zernio dostaje `brak_pliku: true` (zwykle muzyka z biblioteki Instagrama). |
| `transkrybuj` | Robi transkrypcje do `dane/transkrypcje/`. | Pierwszy raz pobiera model (ok. 1,6 GB) i przez kilka minut nic nie wypisuje. Rolka bez mowy dostaje pustą transkrypcję (0 słów), a nie zmyślone zdania. |
| `sprawdz-pule` | Sprawdza pulę i hooki: pliki, frazy, CTA, dopiski, hooki, długość podpisu. | Po każdej ręcznej zmianie `pula.json` i `hooki.json`. Linie „Informacja:” po wyniku to rolki bez mowy: to nie problem. |
| `kadr` | Klatka rolki z próbnym hookiem w `dane/wersje/kadr_KOD.jpg`. | Opcje `--hook-id ID` (hook z `dane/hooki.json`: tekst i emotka z pliku), `--hook "tekst"` (w PowerShellu bez znaków specjalnych), `--emoji E`, `--t SEKUNDA`. Bez nich pierwszy hook z banku rolki. Udane wywołanie nadpisuje ten sam plik rolki (nieudane zostawia poprzednią klatkę). Jak oglądać i pokazać klatkę: krok 6. |
| `pierwsze` | Przygotowuje pierwsze wersje do akceptacji (bez wysyłki do Zernio) i otwiera podgląd. | `--ile 9`. Dorabia do 9, więc po `odrzuc` robi tylko zastępstwa. |
| `podglad` | Tworzy `dane/podglad.html` (wideo, hook, podpis, opis zmian) i otwiera go w przeglądarce. | `--wszystkie`: wersje z ostatnich 14 dni. |
| `akceptuj` | Akceptuje wersje. | `akceptuj TR-001 TR-002` albo `akceptuj --wszystkie`. |
| `odrzuc` | Odrzuca wersje (także z błędem). Ich terminy znów są wolne. | `--powod "tekst"`. Wersji już zaplanowanej tą komendą nie usuniesz. |
| `zaplanuj` | Planuje zaakceptowane wersje w Zernio jako triale MANUAL. | `--na-sucho` pokazuje, co by się stało, bez wysyłki: pyta Zernio o zajęte terminy (tylko odczyt), ale niczego nie wysyła i nie zmienia. Pomija wersję, gdy w Zernio na jej minutę jest już inny post na Instagramie (krok 8 i `PULAPKI.md`). |
| `paczka` | Przygotowuje i planuje wersje na najbliższe dni. | `--dni 7` (domyślnie 7), `--start RRRR-MM-DD`, `--na-sucho`. Prawdziwa odmawia, dopóki żadna wersja nie jest zaplanowana (gdy wersje są już zaakceptowane, mówi, że następny krok to zaplanuj, po zgodzie klienta na pokazane terminy), a potem dopóki jakaś wersja czeka na decyzję klienta („Paczka czeka na decyzję o pierwszych wersjach: N wersji czeka na akceptację klienta (…)”), i kończy się linią „Gotowe. Zaplanowane w Zernio: …”. Plan `--na-sucho` niczego nie renderuje ani nie wysyła, ale tak jak prawdziwa paczka pyta Zernio o zajęte terminy (tylko odczyt) i pokazuje, które z nich pominie (krok 8 i `PULAPKI.md`). Rolkę bez hooków (albo z hookiem lub podpisem, który łamie limity) pomija z ostrzeżeniem „Uwaga: pomijam rolkę …” i robi resztę puli (krok 11 i `PULAPKI.md`). |
| `sprawdz` | Sprawdza w Zernio, co już wyszło, i sprząta pliki wersji starsze niż 14 dni po publikacji. | Wideo zostaje w Zernio. |
| `status` | Lista wersji i ich statusów. Domyślnie tylko z ostatnich 14 dni (także z przyszłymi terminami) i te z błędem, bo po kilku tygodniach wersji są setki. Podsumowanie na górze liczy wszystkie. | `--wszystkie`: wszystkie wersje. Statusy: Do akceptacji, Zaakceptowana, Odrzucona, Zaplanowana, Opublikowana, Błąd. |
| `do-odczytu` | Adresy paneli Instagrama do odczytu wyników (z `?hl=en`): opublikowane triale w wieku od 3 do 35 dni, nieczytane w ostatnich 6 dniach. Bez `--probka` najwyżej 30 adresów, a resztę liczy w linii „Pominięte: N.”. | `--probka`: tylko najnowszy trial każdej rolki, czyli najwyżej jeden adres na rolkę. Z nią czytasz co tydzień, w Chrome i ręcznie. |
| `zapisz-wynik` | Zapisuje wynik wersji (wyświetlenia i obserwujący). | `zapisz-wynik TR-001 --wyswietlenia "1234" --obserwujacy 9` |
| `hamulec` | Liczy hamulec: spadek zasięgu zwykłych rolek. | Paczka robi to sama. |
| `raport` | Raport tygodniowy w `dane/raporty/RRRR-MM-DD.md`. | Pokazuje też najlepsze wersje i błędy. |
| `aktualizuj` | Bez flag pokazuje, czy jest nowa wersja i co się zmieniło. `--sprawdz` tylko zapisuje informację o nowej wersji. `--tak` instaluje. | `--tak` tylko po „tak” klienta. |

## Odczyt liczb z panelu Instagrama

Obserwujących z rolki nie podaje ani Zernio, ani API Mety. Czytamy ich z panelu statystyk rolki na Instagramie: `https://www.instagram.com/insights/media/ID/?hl=en`, gdzie `ID` to numer mediów rolki. Dla kandydata to pole `pk` w `dane/kandydaci.json`, dla rolki z puli pole `media_id` w `dane/pula.json`, a dla wersji adres daje komenda `do-odczytu`. Dopisek `?hl=en` ustawia angielskie etykiety panelu niezależnie od języka konta i niczego nie zmienia na stałe.

**Tryb Chrome** (rozszerzenie Claude in Chrome, klient sam zalogowany na Instagramie):

1. Wypisz skrypt komendą `js-odczyt`. Skrypt tylko czyta tekst strony: niczego nie klika i nie wysyła.
2. Otwórz adres panelu w osobnej karcie Chrome i uruchom na tej karcie skrypt. Czeka do 20 sekund na dane i zwraca tekst JSON: `{"pk", "views_raw", "follows_raw", "lang"}` albo `{"pk", "error", "login", "tekst"}`. Jeśli narzędzie nie przyjmuje `await` na najwyższym poziomie, owiń skrypt w funkcję asynchroniczną i zwróć jego ostatnie wyrażenie.
3. Zapisz liczby dokładnie tak, jak je zwrócił skrypt (np. `12,3 tys.`, `1.2K`, `345,678`). Program rozumie takie skróty. Dla wersji: `zapisz-wynik ID --wyswietlenia "<views_raw>" --obserwujacy "<follows_raw>"`. Dla kandydata: `wynik-kandydata KOD --wyswietlenia "<views_raw>" --obserwujacy "<follows_raw>"`.
4. `login: true` znaczy, że Instagram prosi o logowanie. Zatrzymaj się i poproś klienta, żeby sam zalogował się w tym Chrome. Nigdy nie loguj się za niego. Gdy jest `error` bez `login`, panel się nie wczytał albo ma inne etykiety: odczekaj chwilę i spróbuj jeszcze raz. Jeśli to się powtarza, przejdź na tryb ręczny i zachowaj pole `tekst` do opisu problemu.
5. Gdy Instagram pokaże weryfikację, ostrzeżenie albo prośbę o zgodę, przerwij, niczego nie klikaj i powiedz o tym klientowi. Co tydzień czytasz tylko próbkę z `do-odczytu --probka`, czyli najwyżej jeden adres na rolkę (kilkanaście): czytaj je po kolei, bez pośpiechu, a kartę zamykaj po odczycie. Pełna lista z samego `do-odczytu` rośnie z każdym tygodniem (po miesiącu to ponad 300 triali), więc nie czytaj jej hurtem. Gdy trzy odczyty z rzędu się nie udadzą, przerwij odczyt i powiedz o tym klientowi.
6. Rozszerzenie może zapytać klienta o zgodę na dostęp do instagram.com. To normalne.

**Tryb ręczny:** klient odczytuje liczby w aplikacji Instagram i podaje je tobie. W statystykach rolki są „Wyświetlenia”, a w sekcji „Aktywność w profilu” liczba „Obserwowanie” (ile osób zaczęło obserwować klienta z tej rolki). Nazwy w aplikacji mogą się trochę różnić w zależności od wersji. Gdy klient ich nie znajduje, poproś o opis albo zrzut ekranu. Liczby zapisujesz tymi samymi komendami. Próbną rolkę klient znajdzie po dacie i hooku, więc podaj mu z komendy `status --wszystkie` numer wersji, rolkę, termin i hook (odczytujemy triale sprzed 3–35 dni, a samo `status` pokazuje tylko ostatnie 14). Komenda `do-odczytu --probka` zawęża listę do najnowszego triala każdej rolki (najwyżej 12 par liczb na tydzień).

## Dane klienta: config.json, pula.json, hooki.json

Pliki w `dane/` (poza `dane/.env`, do którego nie masz dostępu) edytujesz narzędziem do edycji plików, a nie komendami. Zachowaj UTF-8, polskie znaki i poprawny JSON (przecinki, proste cudzysłowy wokół tekstów). Typograficzne cudzysłowy „…” w środku tekstu zostaw takie, jakie są: po nich program rozpoznaje słowo-klucz. Po każdej zmianie `pula.json` albo `hooki.json` uruchom `sprawdz-pule`. Nie zmieniaj `code` ani `media_id` i nie ruszaj `stan.json` ani `kreator.json` (zapisują je komendy). Plik `kandydaci.json` zapisują komendy `kandydaci` i `wynik-kandydata`. Nie edytujesz go i nie wczytujesz w całości (to kilkadziesiąt KB): rolek wykreślonych przez klienta w kroku 4 nie usuwasz z niego, tylko nie podajesz ich do puli (komenda `pula KOD …` z kodami rolek, które zostały).

### config.json: ustawienia

Zapisują się tylko te ustawienia, które klient zmienił. Resztę program bierze z domyślnych, takich jak tu:

```json
{
  "timezone": "Europe/Warsaw",
  "day_window": ["07:15", "22:00"],
  "hours": ["09:00", "21:00"],
  "daily_max": 10,
  "brake_slot": "13:00"
}
```

- `timezone`: strefa czasowa klienta w formie `Europe/Warsaw`.
- `day_window`: okno publikacji. Nic nie wychodzi poza nim.
- `hours`: pierwsza i ostatnia godzina triali w ciągu dnia. Terminy rozkładają się między nimi równo (przy 10 dziennie co 80 minut).
- `daily_max`: najwyżej tyle triali dziennie. Dziennie idzie tyle triali, ile wynosi to ustawienie, ale nie więcej niż aktywnych rolek w puli, a żadna rolka nie idzie dwa razy tego samego dnia.
- `brake_slot`: godzina jedynego triala dziennie, gdy włączy się hamulec. Domyślnie 13:00, czyli pełna godzina: gdy przesuwasz `hours` (np. na 09:05–21:05), przesuń też `brake_slot` (np. na 13:05), bo inaczej przy włączonym hamulcu trial wypadnie na pełną godzinę, o której klient może publikować coś innego.
- `ig_account_id` i `ig_handle` zapisuje komenda `konto`. Nie ruszaj ich ręcznie.

`hours` i `brake_slot` muszą mieścić się w `day_window`. Po każdej edycji `config.json` uruchom `doktor`: wiersz „Ustawienia (dane/config.json)” pokaże, czy plik da się wczytać, a wiersz „Strefa czasowa”, czy strefa jest znana. Ustawienia zmieniasz tylko na prośbę klienta albo za jego zgodą, na przykład gdy komenda `paczka` podpowie mniejszą liczbę triali przez wolny komputer.

### pula.json: rolki

Lista rolek. Pola `code`, `name`, `media_id`, `caption`, `active` i `hook_y` dopisuje komenda `pula`. Resztę ustawiasz ty, zawsze po zatwierdzeniu przez klienta. Poniżej wszystkie pola naraz (w prawdziwej rolce większość z nich nie występuje):

```json
{
  "code": "Cabc123XYZ_",
  "name": "Jak wybrać pierwszy zabieg",
  "caption": "Zobacz, od czego zacząć.\n\nNapisz „PRZEWODNIK” w komentarzu, a wyślę ci poradnik. Zaobserwuj @przyklad.konto",
  "active": true,
  "hook_y": 0.17,
  "mask": {"y": 0.45, "min_w": 0.9, "min_h": 0.12},
  "blur": [{"t": [10.8, 13.4], "box": [0.0, 0.05, 1.0, 0.3]}],
  "cuts": [{"from": "napisz przewodnik", "to": "w komentarzu"}],
  "strong": "to jest najmocniejsze zdanie rolki",
  "cta": "Napisz „PRZEWODNIK” w komentarzu, a wyślę ci poradnik. Zaobserwuj @przyklad.konto",
  "cta_variants": [
    "Skomentuj „PRZEWODNIK”, a wyślę ci poradnik. Zaobserwuj @przyklad.konto",
    "Zostaw „PRZEWODNIK” pod rolką i obserwuj @przyklad.konto"
  ],
  "extras": [
    "Zapisz sobie na później.",
    "Wyślij to komuś, kto tego potrzebuje.",
    "Wróć do tego za tydzień.",
    "Pokaż to osobie, której ufasz."
  ],
  "ustawienia_ok": true,
  "hooki_ok": true
}
```

- `name`: krótka, czytelna nazwa dla klienta (możesz ją poprawić).
- `caption`: oryginalny podpis rolki. To tekst bazowy podpisów wersji.
- `active`: `false` wyłącza rolkę (np. gdy Zernio nie ma jej pliku).
- `hook_y`: pozycja środka dymka z hookiem od góry kadru (0 to góra, 1 to dół, domyślnie 0,17). Program sam pilnuje, żeby dymek nie wyszedł poza bezpieczny obszar kadru.
- `mask`: dymek z hookiem trwa przez całą rolkę i zasłania wypalony napis. `y` to pozycja środka dymka, a `min_w` i `min_h` to minimalna szerokość i wysokość dymka jako ułamek kadru (dymek ma być co najmniej tak duży jak napis pod nim).
- `blur`: rozmycie fragmentów kadru, np. cudzych danych na ekranie. `t` to [od, do] w sekundach nagrania źródłowego, a `box` to [x, y, szerokość, wysokość] jako ułamki kadru (0–1). Wpisuj same liczby, a pasek ma się mieścić w kadrze: inny wpis `sprawdz-pule` zgłosi jako problem, a render go odrzuci.
- `cuts`: wycięcia z rolki. `from` i `to` to frazy dosłownie z transkrypcji: wycina od początku `from` do końca `to`, a bez `to` do końca rolki. Typowo: wypowiedziane zaproszenie ze słowem-kluczem, które u klienta nie działa.
- `strong`: najmocniejsze zdanie rolki, dosłownie z transkrypcji. Od niego zaczyna się wersja „mocna” (zimne otwarcie: rolka najpierw pokazuje to zdanie, a potem leci od początku). Bez `strong` rolka nie dostaje wersji mocnych.
- Rolka bez mowy (transkrypcja ma 0 słów, np. sama muzyka i napisy na ekranie) nie ma czego cytować: nie ustawiasz jej `strong` ani `cuts`, a `sprawdz-pule` pisze o niej tylko „Informacja:”. Taka rolka dostaje wersje Subtelną i Średnią, bez Mocnej. Gdy mimo to ma `strong` albo `cuts`, `sprawdz-pule` zgłosi problem i każe je usunąć.
- `cta`, `cta_variants`, `extras`: zaproszenie do działania, jego warianty i dopiski (zasady niżej). `cta` jest opcjonalne.
- `ustawienia_ok`, `hooki_ok`: ustawiasz na `true` dopiero po zatwierdzeniu przez klienta (kroki 6 i 7). Bez nich `krok` nie uzna tych kroków za gotowe.
- `brak_pliku` ustawia komenda `pobierz`, a znika, gdy plik się pojawi.

### hooki.json: banki hooków

Obiekt, w którym kluczem jest kod rolki, a wartością lista hooków tej rolki:

```json
{
  "Cabc123XYZ_": [
    {"id": "h01", "text": "Zrób to przed pierwszą wizytą", "emoji": "👉"},
    {"id": "h02", "text": "3 rzeczy, które robisz za wcześnie", "emoji": "🤔"},
    {"id": "h03", "text": "Nikt ci o tym nie powiedział?", "emoji": "👀"},
    {"id": "h04", "text": "Sprawdź to, zanim zapłacisz", "emoji": "🛑"},
    {"id": "h05", "text": "Dlaczego to nie działa u ciebie?", "emoji": "😮"}
  ]
}
```

Każdy hook ma unikalne `id` w obrębie rolki, `text` i `emoji`. Przykład pokazuje bank na start: 5 hooków na rolkę.

## Hooki, podpisy i dopiski

**Hook** to napis w białym dymku na początku rolki. Ma zatrzymać obcego widza.

- Szeroki: objaw, pragnienie, liczba albo kontrowersja. Bez etykiety niszy w pierwszych sekundach: nie „Jesteś księgową?”, tylko to, co widz czuje albo czego chce.
- Do 50 znaków. To twardy limit: dłuższy hook odrzuci `sprawdz-pule`.
- Jedna prosta emotka z dołączonego zestawu, w polu `emoji`, a nie w tekście. Zapisuj ją bez niewidocznego znaku U+FE0F. Nie kopiuj emotek skądinąd, tylko z listy niżej.
- Dopowiada to, co pada na starcie rolki, a nie powtarza tego słowo w słowo.
- Styl bierzesz z rolek klienta (transkrypcja: jego słownictwo, długość zdań, ton), a nie z własnego głosu. Rolka bez mowy (transkrypcja ma 0 słów) nie ma czego cytować: hook i podpis bierzesz wtedy z jej podpisu (`caption`) i z obrazu (klatki z `kadr`, napisy na ekranie). Gdy podpis jest pusty albo nic nie mówi, zapytaj klienta jednym zdaniem, o czym jest rolka. Transkrypcji takiej rolki nie cytujesz.
- Na start piszesz 5 hooków na rolkę, każdy z unikalnym `id` (h01, h02…). Program wymaga co najmniej 3 hooki na rolkę. Pisanie możesz rozłożyć na kilka posiedzeń (po kilka rolek naraz). Gdy bank się wyczerpie (przy 5 hookach zwykle w pierwszym tygodniu), idą powtórki najlepszych hooków (z inną emotką), więc pusty bank niczego nie blokuje, a program napisze tylko „Bank hooków prawie pusty” (po prawdziwej `paczka` i w planie na sucho, który liczy bank tak, jakby wersje z planu już powstały). W planie na sucho powtórzony hook ma jeszcze emotkę z banku, a gotowa wersja dostaje inną. Więcej hooków dopisujesz później, na osobnym posiedzeniu, gdy klient ma na to czas i limit. Odświeżony hook (skrócony albo wydłużony zwycięzca) dopisz na końcu listy z kolejnym `id`.
- Lista kontrolna przed pokazaniem klientowi: hook nie przeczy temu, co mówi rolka. Nie obiecuje niczego, czego klient w rolce nie powiedział (liczb, terminów, wyników). Mieści się w limicie. Nie ma w nim długiego myślnika.

Dostępne emotki (30): 🎯 🏆 👀 👇 👉 💡 💪 💬 💰 📈 📌 📱 🔥 😅 😎 😮 😳 🙌 🚀 🛑 🤔 🤯 🧠 ⏰ ⚡ ✅ ✨ ❌ ❤ ⭐

**Podpis** wersji powstaje z oryginalnego podpisu rolki (`caption`): program podmienia w nim zaproszenie do działania na kolejne warianty i dopisuje na końcu jeden dopisek. Pierwsza linia zostaje bliska oryginałowi, bo zaproszenie ma być takie, jak było.

- `cta`: dokładny fragment `caption` z zaproszeniem do działania. Skopiuj go znak w znak. Pole jest opcjonalne: gdy podpis rolki nie ma żadnego zaproszenia, nie ustawiaj `cta` ani `cta_variants` i nie dopisuj zaproszenia do `caption` na siłę. Podpis wersji to wtedy oryginalny podpis plus jeden dopisek z `extras`, a `sprawdz-pule` nie zgłasza braku `cta`.
- `cta_variants`: inne sformułowania tego samego zaproszenia. Każdy wariant zachowuje @nick i słowo-klucz w „…” (jeśli były w `cta`). Oryginał zostaje w rotacji. Bez `cta` warianty nie są używane.
- `extras`: co najmniej 4 dopiski, czyli krótkie zdania doklejane na końcu podpisu. Piszesz je tylko z tego, co klient mówi w tej rolce: bez nowych faktów, obietnic i liczb.
- W wariantach i dopiskach nie ma długiego myślnika. Podpis ma najwyżej 2200 znaków (program sprawdza podpisy wszystkich wersji, aż zaczną się powtarzać).
- Słowo-klucz w `cta` zostaje tylko wtedy, gdy klient potwierdzi, że jego automatyczna odpowiedź (wiadomość po wpisaniu słowa w komentarzu) działa pod nowymi postami, także pod próbnymi rolkami. Gdy nie działa albo klient nie ma pewności, zamień w `caption` to zdanie na zwykłe zaproszenie (np. „Zaobserwuj @przyklad.konto, jeśli chcesz więcej takich treści”), wpisz w `cta` dokładnie to samo zdanie (znak w znak, tak jak stoi w `caption`) i, jeśli rolka ma mowę, dodaj w `cuts` wycięcie wypowiedzianego zaproszenia z nagrania.

## Cykl tygodniowy

Raz w tygodniu (w niedzielę o 18:00 w zadaniu zaplanowanym w aplikacji Claude albo na prośbę klienta „zrób paczkę na tydzień”) robisz po kolei:

1. `krok`: tylko wgląd w alerty i tryb pomiaru.
2. `sprawdz`.
3. `aktualizuj --sprawdz`: tylko informacja, że jest nowa wersja. Niczego nie instaluje.
4. Odczyt wyników: w trybie Chrome przez `do-odczytu --probka`, `js-odczyt` i `zapisz-wynik` (najwyżej jeden trial na rolkę), w trybie ręcznym pomijasz go i prosisz klienta o liczby przy najbliższej rozmowie.
5. `paczka --dni 7`: uruchom ją w tle i poczekaj na powiadomienie o jej końcu (linia „Gotowe. Zaplanowane w Zernio: …”), bez sprawdzania w pętli. Gdy skończy się błędem, uruchom ją jeszcze raz w tle, najwyżej 3 razy: pomija gotowe terminy.
6. `raport` i krótkie podsumowanie dla klienta, dopiero po jej końcu.

Szczegóły i gotowy prompt zadania są w `kroki/10-tydzien.md`. Gdy `paczka` pominie wersje, bo w Zernio jest już inny post na ich termin, w zadaniu tygodniowym niczego nie przestawiaj ani nie odrzucaj: opisz to w podsumowaniu, a poprawicie to z klientem w rozmowie (patrz `PULAPKI.md`).

## Alerty z komendy krok

1. „Na jutro nie ma żadnego triala. Zrób paczkę na najbliższy tydzień: komenda paczka --dni 7.” Zwykle komputer przespał niedzielę. Zaproponuj klientowi zrobienie paczki teraz i po jego „tak” uruchom `paczka --dni 7`. Jest bezpieczna po przerwie: pomija zajęte terminy i kończy wersje, które nie mają jeszcze posta. Alert pojawia się też od razu po kroku 9, gdy pierwsze wersje nie sięgają jutra. To zamierzone, bo krok 10 zaczyna się od pierwszej paczki.
2. „N wersji z błędem. Komenda status pokaże, które…” Powód błędu podaje `raport` (sekcja „Błędy”). Napraw przyczynę (patrz `PULAPKI.md`) i uruchom `paczka` jeszcze raz: zrobi nową wersję na wolny termin. Albo odrzuć wersję komendą `odrzuc ID`.
3. „Rolka NAZWA (KOD) nie ma hooków w dane/hooki.json, więc paczka ją pomija. Dopisz co najmniej 3 hooki i uruchom sprawdz-pule (dla nowej rolki to krok 7).” Zwykle klient dodał rolkę komendą `pula`, a rozmowa urwała się, zanim powstały jej hooki. Paczka robi wtedy wersje z pozostałych rolek, a tę pomija z ostrzeżeniem („Uwaga: pomijam rolkę …”). Dokończ dla niej kroki 5, 6 i 7 (patrz `kroki/11-codziennie.md`) albo, za zgodą klienta, ustaw jej `"active": false`. Alert pojawia się dopiero po tym, jak pierwsze wersje trafiły do Zernio, a przy kilku rolkach zaczyna się od „Rolki …”.
4. „Jest nowa wersja vX.Y.Z (masz A.B.C)…” Postępuj tak, jak opisuje „Aktualizacja”.

## Aktualizacja

1. Komenda `aktualizuj` (bez flag) pokazuje, czy jest nowa wersja i co się zmieniło. Przetłumacz zmiany klientowi prostym językiem.
2. Zapytaj, czy aktualizować. Tylko po wyraźnym „tak” uruchom `aktualizuj --tak`. Aplikacja jeszcze raz zapyta o zgodę na tę komendę (zawsze pyta). Uprzedź o tym klienta.
3. Nie aktualizuj, gdy w tle działa `paczka` albo `pierwsze`.
4. Aktualizacja podmienia kod, skill, `CLAUDE.md` i `.claude/settings.json`. Własne zmiany klienta w tych plikach znikną, a `.claude/settings.local.json` jest bezpieczny. Foldery `dane/` i `.venv/` zostają nietknięte. Gdy zmienił się `requirements.txt`, doinstalowanie pakietów trwa kilka minut (uruchom w tle). Na końcu aktualizacja sama uruchamia `doktor`.
5. Przerwana aktualizacja (np. zajęty plik na Windowsie) cofa się sama. Poproś klienta o zamknięcie programów, które mogą trzymać pliki (przeglądarka z podglądem, antywirus), i uruchom `aktualizuj --tak` jeszcze raz. Po twardym przerwaniu (wyłączony komputer, brak prądu) postępuj tak, jak opisuje `PULAPKI.md` („Aktualizacja przerwana w połowie”).
6. Gdy po aktualizacji pakiety się nie doinstalowały, powtórz instalację pakietów z kroku „Programy” (`kroki/01-programy.md`) i uruchom `doktor`. Jeśli sam `uv` nie działa w powłoce, wołaj go pełną ścieżką (Mac `~/.local/bin/uv`, Windows `%USERPROFILE%\.local\bin\uv.exe`).

## Pojęcia i jak je tłumaczyć

Wyjaśniaj każde pojęcie przy pierwszym użyciu, prostymi słowami:

- **Trial reel (próbna rolka):** rolka, którą Instagram pokazuje tylko osobom, które klienta jeszcze nie obserwują. Nie ma jej w siatce profilu, więc nie zaśmieca profilu i nie widzą jej obserwujący. Jej wynik pokazuje, czy rolka przyciąga nowych ludzi.
- **Zernio:** usługa, która publikuje rolki na Instagramie o zaplanowanej godzinie. Ma dostęp do konta klienta za jego zgodą. Program przygotowuje rolki i zleca Zernio ich publikację.
- **Klucz API:** długi tajny ciąg znaków, coś jak hasło dla programu do Zernio. Leży w pliku `dane/.env` i nigdy nie trafia do czatu.
- **Hook:** napis w białym dymku na początku rolki (pierwsze ok. 3 sekundy), który ma zatrzymać obcego widza.
- **CTA (zaproszenie do działania):** zdanie w rolce i w podpisie, które mówi widzowi, co zrobić dalej, np. „napisz SŁOWO w komentarzu” albo „zaobserwuj @nick”.
- **Słowo-klucz:** słowo, które widz ma wpisać w komentarzu, żeby dostać wiadomość z materiałem (automatyczna odpowiedź klienta).
- **Transkrypcja:** zapis tego, co klient mówi w rolce, ze znacznikami czasu. Mów „zapis tego, co mówisz”. Rolka bez mowy (sama muzyka, napisy na ekranie) ma transkrypcję pustą.
- **Render:** przygotowanie pliku wideo z hookiem i zmianami. Mów „przygotowanie wersji”.
- **Wersja (TR-001…):** jedna próbna odmiana rolki, z hookiem, podpisem i terminem.
- **Pula:** rolki, z których powstają wersje (do 12).
- **Paczka:** komplet wersji na kolejne dni, zwykle na tydzień.
- **MANUAL:** do obserwujących puszcza triala tylko klient, ręcznie w aplikacji Instagram.
- **Hamulec:** automatyczne ograniczenie do 1 triala dziennie, gdy zasięg zwykłych rolek wyraźnie spada.

## Gdy klient utknie

Jeśli ani ty, ani `PULAPKI.md` nie rozwiązujecie problemu (albo klient o to prosi), napisz klientowi opis problemu do wklejenia opiekunowi, czyli osobie, która poleciła mu ten program, tam gdzie zwykle się z nią kontaktuje:

- system (Mac albo Windows) i wersja programu (komenda `wersja`),
- numer i nazwa kroku oraz to, co klient chciał zrobić,
- komenda i komunikat dosłownie (jedna linia),
- co już próbowaliście,
- skrót wyniku komendy `doktor`.

W opisie nie ma kluczy, zawartości `dane/.env`, haseł ani cudzych danych z ekranu. Pokaż klientowi opis przed wysłaniem: to on go wkleja.
