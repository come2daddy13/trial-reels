**Krok 5: Pliki i transkrypcje**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Pobieramy pliki wideo wybranych rolek i robimy ich transkrypcje, czyli zapis tego, co mówisz, ze znacznikami czasu.

## Po co

Do przygotowania wersji potrzebujemy oryginalnych plików. Transkrypcja pozwala programowi znaleźć w rolce konkretne zdania: wyciąć zaproszenie do działania albo zacząć rolkę od najmocniejszego zdania. Rozpoznawanie mowy działa na twoim komputerze. Za pierwszym razem pobiera się do niego model (ok. 1,6 GB), potem już nie.

## Co robisz Ty

1. Poczekaj. Pobieranie plików to kilka minut. Transkrypcja za pierwszym razem trwa dłużej: najpierw pobiera się model (ok. 1,6 GB), a potem każda rolka liczy się od kilkudziesięciu sekund do kilku minut, zależnie od komputera. Przez długi czas nic nie pojawia się na ekranie. To normalne, nie przerywaj. Komputer może chodzić wolniej.
2. Przy rolce z muzyką z biblioteki Instagrama zdecyduj: pomijamy ją (zwykle najlepiej, bo wersje wyszłyby bez tej muzyki) albo masz oryginalny plik wideo tej rolki (z telefonu albo z edytora) i wrzucasz go do folderu, który ci otworzę, pod nazwą z kodem rolki, którą podam.
3. Jeśli któraś rolka nie ma mowy (sama muzyka albo napisy na ekranie), powiem ci o niej. To nie błąd. Zdecyduj, czy ją zostawiamy (hooki i podpis ułożę z jej opisu i z obrazu, a wyjdą z niej tylko wersje Subtelna i Średnia), czy pomijamy.
4. Gdy transkrypcje będą gotowe, to dobry moment na przerwę. Postęp jest zapisany w plikach i wrócimy do kroku 6 w nowej rozmowie.

## Co robię ja

1. Uruchamiam `bash trial.sh pobierz` albo `.\trial.cmd pobierz`. Pliki trafiają do `dane/src/`. Rolka, której Zernio nie ma, dostaje `brak_pliku: true` i komunikat „Zernio nie ma jej pliku…”.
2. Dla każdej takiej rolki pytam klienta o decyzję. Pomijanie: w `dane/pula.json` ustawiam `"active": false`, dopisuję zastępstwo kodem kolejnej rolki z listy kandydatów, którą klient zostawił (`bash trial.sh pula KOD` albo `.\trial.cmd pula KOD`; `pula --auto 12` tylko wtedy, gdy klient niczego z listy nie wykreślał) i uruchamiam `pobierz` jeszcze raz. Własny plik: otwieram folder `dane/src` (Mac: `open dane/src`, Windows w PowerShellu: `explorer dane\src`, w Git Bash: `explorer "dane\src"`) i mówię, jak nazwać plik: `KOD.mp4`, gdzie `KOD` to kod rolki, a rozszerzenie to dokładnie `mp4`.
3. Uruchamiam `bash trial.sh transkrybuj` albo `.\trial.cmd transkrybuj`. Robię to w tle i uprzedzam klienta o pierwszym pobieraniu modelu.
4. Pokazuję pulę: `bash trial.sh pula` albo `.\trial.cmd pula`.
5. Szukam rolek bez mowy. Program rozpoznaje je sam: `transkrybuj` zapisuje dla nich pustą transkrypcję (0 słów), a nie zmyślone zdania. Uruchamiam `bash trial.sh sprawdz-pule` albo `.\trial.cmd sprawdz-pule` tylko po to, żeby znaleźć linie zaczynające się od „Informacja:”, na przykład: „Informacja: Rolka NAZWA (KOD): rolka bez mowy (transkrypcja ma 0 słów), więc nie potrzebuje pól strong ani cuts. Poziom zmian Mocna jej nie dotyczy, bo nie ma zdania na zimne otwarcie.” Reszta wyniku (braki hooków i dopisków) jest na tym etapie normalna: uzupełnimy je w krokach 6 i 7, więc nie wklejam jej klientowi. Klientowi podaję tylko nazwy rolek bez mowy i pytam, czy je zostawiamy.
6. Dalej według decyzji klienta. Gdy rolka bez mowy zostaje: hooki i podpis biorę z jej podpisu (`caption`) i z obrazu, `strong` zostaje puste, `cuts` nie ustawiam, a transkrypcji nie cytuję (jest pusta). Taka rolka dostaje tylko wersje Subtelną i Średnią. Gdy ją pomijamy: ustawiam `"active": false`, dopisuję zastępstwo jak w punkcie 2 i uruchamiam `pobierz` oraz `transkrybuj` jeszcze raz.
7. Po zakończeniu kroku proponuję klientowi przerwę (patrz „Oszczędzaj limit klienta” w `CLAUDE.md`). Jeśli chce iść dalej, przechodzę do kroku 6.

## Jak sprawdzamy

Komenda `pula` pokazuje „tak” w kolumnach „Plik” i „Transkrypcja” przy każdej aktywnej rolce (rolka bez mowy też ma „tak”: plik z transkrypcją jest, tylko pusty). `krok` pokazuje krok `pliki` jako gotowy („Wszystkie aktywne rolki (N) mają plik i transkrypcję.”).

## Gdy nie wychodzi

- `pobierz` kończy się z nieudanymi plikami (zwykle przez sieć). Uruchom go jeszcze raz. Pliki, które już są, zostają pominięte.
- `transkrybuj` pisze „Nie udało się wczytać modelu rozpoznawania mowy”. Najczęściej brakuje internetu przy pobieraniu modelu albo miejsca na dysku. Sprawdź internet i uruchom `doktor`, a potem `transkrybuj` jeszcze raz. Gotowe transkrypcje są pomijane.
- `transkrybuj` długo nic nie pisze. Przy pierwszym pobieraniu modelu to normalne. Poczekaj do 10 minut, zanim zaczniesz podejrzewać błąd.
- Komputer bardzo zwalnia. Powiedz klientowi, że to chwilowe i po transkrypcji wróci do normy.
- Krok `pliki` nadal jest niegotowy przez rolkę z `brak_pliku`. Dopóki klient nie wrzuci oryginału albo rolka nie dostanie `"active": false`, krok się nie zamknie. Pole `szczegoly` podpowiada, co zrobić.
- Własny plik klienta nie jest znajdowany. Nazwa musi brzmieć dokładnie `KOD.mp4` (kod rolki z `dane/pula.json`, rozszerzenie `mp4`) i plik musi leżeć w `dane/src`.
- Transkrypcja rolki, w której nikt nie mówi, ma zmyślone zdania (np. „Dzięki za oglądanie!”, zdanie po angielsku albo samo „KONIEC”). Tak robiły transkrypcje zrobione bez filtra głosu, czyli starsze wersje programu. Nie cytuj ich. Za zgodą klienta usuń `dane/transkrypcje/KOD.json` (powiedz mu, że to tylko zapis tego, co mówi rolka, i że zrobi się od nowa) i uruchom `transkrybuj` jeszcze raz: rolka dostanie wtedy pustą transkrypcję.
- `transkrybuj` wypisuje po angielsku ostrzeżenia biblioteki (np. „Warning: You are sending unauthenticated requests to the HF Hub…” albo „Tip: experimental MPS backend…”). To szum, a nie błąd (patrz `PULAPKI.md`).
