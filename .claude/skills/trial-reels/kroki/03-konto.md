**Krok 3: Konto Instagram**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Wybieramy w Zernio konto Instagram, z którego program będzie korzystał, i sprawdzamy, czy widzi twoje rolki.

## Po co

W Zernio może być podłączonych kilka kont. Program musi wiedzieć, które jest twoje, bo z niego czyta rolki i na nim planuje triale. Przy okazji ten test od razu pokaże, czy klucz do Zernio działa.

## Co robisz Ty

1. Potwierdź, że pokazany nick to twoje konto na Instagramie.
2. Jeśli w Zernio masz kilka kont, wskaż to, którego używamy do trial reels.

## Co robię ja

1. Uruchamiam `bash trial.sh konto` albo `.\trial.cmd konto`. Program pokazuje listę kont Instagrama z Zernio i, gdy jest jedno, zapisuje je.
2. Gdy kont jest kilka, pytam, które jest właściwe, i uruchamiam komendę z jego nickiem: `bash trial.sh konto --nick moje.konto` albo `.\trial.cmd konto --nick moje.konto`.
3. Czytam wynik testu: „Test odczytu się udał. Rolek z ostatnich 30 dni: N.”

## Jak sprawdzamy

Komenda pisze „Zapisałem konto @nick.” i „Test odczytu się udał.” Potem `krok` pokazuje krok `konto` jako gotowy („Konto @nick.”). Klient potwierdza, że nick się zgadza.

## Gdy nie wychodzi

- „Zernio nie ma podłączonego konta Instagrama.” Wróć do kroku 2 i podłącz Instagram w panelu Zernio.
- „Zernio nie przyjęło klucza z dane/.env” (kod 401 albo 403). Klucz został wklejony niepełny albo jest nieaktualny. Utwórz w Zernio nowy klucz i wklej go do pliku, który otworzy komenda `klucz` (jak w kroku 2).
- „Zernio żąda płatności za tę funkcję” (kod 402). Zernio mówi, że ta funkcja, zwykle statystyki rolek, wymaga innego planu. Poproś klienta o sprawdzenie planu i aktualnego cennika w panelu Zernio. Bez statystyk nie wybierzemy rolek.
- „Zernio prosi o zwolnienie tempa” (kod 429). Poczekaj minutę i uruchom komendę jeszcze raz.
- „Konto jest zapisane, ale test odczytu rolek się nie udał.” Popraw przyczynę podaną w komunikacie (klucz, plan, internet) i uruchom `konto` jeszcze raz.
- „Rolek z ostatnich 30 dni: 0.” To nie błąd. Wybór rolek w następnym kroku patrzy na 12 miesięcy.
- „Nie mogę połączyć się z Zernio.” Sprawdź internet.
- Klient chce obsługiwać dwa konta na Instagramie. Jedna instalacja obsługuje jedno konto. Drugie konto wymaga osobnego folderu `trial-reels` i osobnej konfiguracji od kroku 0.
