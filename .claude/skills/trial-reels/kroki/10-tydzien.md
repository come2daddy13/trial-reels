**Krok 10: Paczka co tydzień**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Robimy pierwszą paczkę wersji na tydzień i ustawiamy w aplikacji Claude zadanie, które co niedzielę o 18:00 robi kolejną samo.

## Po co

Ta metoda opiera się na regularnych próbach: codziennie do 10 nowych wersji, a co tydzień sprawdzamy w liczbach, co działa. Robienie tego ręcznie co niedzielę szybko by się znudziło, więc po pierwszej paczce przekazujemy to zadaniu zaplanowanemu. Ty oglądasz tylko krótkie podsumowanie.

## Co robisz Ty

1. Poczekaj na pierwszą paczkę. Przygotowanie wersji na cały tydzień (to zwykle kilkadziesiąt wersji) może potrwać od kilkunastu minut do godziny albo dłużej, zależnie od komputera. W tym czasie komputer ma być włączony, a aplikacja Claude otwarta.
2. Jeśli program podpowie mniejszą liczbę triali dziennie, bo przygotowanie wersji idzie wolno, zdecyduj, czy zmniejszamy. Domyślnie zostaje 10 dziennie. Decyzja jest twoja.
3. Zadanie zaplanowane uruchamia się zwykle tylko wtedy, gdy w niedzielę o 18:00 komputer jest włączony, a aplikacja Claude otwarta. Jeśli nie, nic się nie psuje: przy następnej rozmowie poproszę o zrobienie paczki (patrz „Gdy nie wychodzi”).
4. Pierwsze uruchomienie zadania robimy razem. Aplikacja zapyta o zgody na narzędzia i komendy. Wybierz „zawsze zezwalaj”, żeby kolejne uruchomienia szły bez pytań.
5. Jeśli wybrałeś(-aś) w kroku 9 tryb Chrome, w niedzielę o 18:00 Chrome ma być otwarty i zalogowany na Instagramie. Jeśli nie będzie, zadanie pominie odczyt wyników i zrobi resztę.

## Co robię ja

1. Zaczynam od planu na sucho: `bash trial.sh paczka --dni 7 --na-sucho` albo `.\trial.cmd paczka --dni 7 --na-sucho`. Pokazuję klientowi, ile wersji pójdzie, w jakich dniach i czy hamulec jest włączony. Plan na sucho pyta Zernio o zajęte terminy (tylko odczyt, niczego nie wysyła), więc pokazuje też terminy, które prawdziwa paczka pominie: linie „! RRRR-MM-DD GG:MM (nazwa rolki): na ten termin masz już inny post na Instagramie. Pomijam ten termin.”, zdanie „Na sucho: zaplanowałbym X z Y. Nic nie wysłałem i nic nie zmieniłem.” i wskazówkę o przesunięciu godzin. Gdy są pominięcia, najpierw omawiam je z klientem (patrz „Gdy nie wychodzi”).
2. Po zgodzie klienta uruchamiam pierwszą paczkę w tle: `bash trial.sh paczka --dni 7` albo `.\trial.cmd paczka --dni 7`. Czekam na powiadomienie o jej końcu i nie sprawdzam jej w pętli. Gdy się przerwie albo skończy błędem (zamknięta aplikacja, uśpiony komputer), uruchamiam ją jeszcze raz: pomija zajęte terminy i nic nie dubluje.
3. Gdy paczka się skończy, pokazuję krótkie podsumowanie z komendy `status` (`bash trial.sh status` albo `.\trial.cmd status`).
4. Tworzę zadanie zaplanowane. Jeśli mam do tego narzędzie, ustawiam: nazwę „Trial reels: tydzień”, powtarzanie co niedzielę o 18:00 w czasie klienta, ten folder i poniższy prompt. Jeśli narzędzia nie mam, pokazuję klientowi, gdzie w aplikacji dodać zadanie zaplanowane, i daję prompt do wklejenia. Jeśli i to się nie uda, zostaje wariant bez zadania: w niedzielę klient pisze „zrób paczkę na tydzień”.

   ```
   Pracujesz w folderze trial-reels (program do próbnych rolek na Instagramie). To zadanie tygodniowe działa bez klienta, więc nie zadawaj pytań. Wykonaj kroki po kolei i na końcu napisz podsumowanie.

   Zasady:
   - Nie loguj się za klienta i nie proś o hasła. Gdy strona prosi o logowanie, przerwij tę część i zapisz to w podsumowaniu.
   - Publikuj tylko w godzinach okna publikacji (komendy same tego pilnują) i nie ustawiaj innego trybu niż MANUAL.
   - Nigdy nie czytaj ani nie wypisuj dane/.env (ani narzędziem do czytania plików, ani komendami cat, type, Get-Content, grep).
   - Nie aktualizuj programu. Tylko sprawdź, czy jest nowa wersja.
   - Nie zmieniaj ustawień ani wersji na własną rękę. Gdy program podpowiada coś do zrobienia (np. przesunięcie godzin triali albo odrzucenie pominiętych wersji), przepisz tę podpowiedź do podsumowania i jej nie wykonuj.
   - Komendy wołaj tak, jak opisuje CLAUDE.md: `bash trial.sh <komenda>` (Mac, Git Bash) albo `.\trial.cmd <komenda>` (PowerShell).

   Kroki:
   1. `krok`: zapamiętaj tryb pomiaru (krok „pomiar”, pole szczegoly: „Zapisane: chrome.” albo „Zapisane: reczny.”) i alerty.
   2. `sprawdz`.
   3. `aktualizuj --sprawdz`. To tylko informacja o nowej wersji. Jeśli komenda się nie uda (np. brak internetu), idź dalej.
   4. Odczyt wyników. W trybie chrome uruchom `do-odczytu --probka` (zawsze z --probka, bo pełna lista rośnie z każdym tygodniem): wypisuje najwyżej jedną linię na rolkę, jej najnowszą wersję, w postaci „TR-001  adres”. Dla każdej linii otwórz adres w osobnej karcie Chrome, uruchom skrypt z `js-odczyt` i zapisz wynik komendą `zapisz-wynik TR-001 --wyswietlenia "<views_raw>" --obserwujacy "<follows_raw>"` (numer wersji TR-… bierz z początku tej samej linii, a nie z adresu). Gdy Instagram prosi o logowanie albo pokazuje ostrzeżenie, przerwij odczyt i zapisz to w podsumowaniu. Gdy trzy odczyty z rzędu się nie udadzą, też przerwij odczyt i zapisz to w podsumowaniu: paczka nie może czekać na odczyt. W trybie reczny pomiń odczyt i napisz w podsumowaniu, że wyniki trzeba przepisać ręcznie (komenda do-odczytu --probka).
   5. `paczka --dni 7`. Uruchom ją jako polecenie w tle (opcja run_in_background narzędzia do komend), bo paczka na tydzień trwa dłużej niż limit 10 minut jednej komendy. Poczekaj na powiadomienie o jej końcu i nie sprawdzaj jej wyniku w pętli ani co chwilę. Paczka kończy się linią „Gotowe. Zaplanowane w Zernio: …” albo „Nie ma wolnych terminów…”. Nie przechodź do kroku 6, dopóki paczka się nie skończy. Jeśli skończy się błędem (kod wyjścia inny niż 0), uruchom ją jeszcze raz tak samo, w tle, najwyżej 3 razy: pomija terminy, które już są gotowe, i nic nie dubluje. Jeśli po trzecim ponowieniu nadal kończy się błędem, przejdź do kroku 6 i napisz w podsumowaniu, że paczka jest niedokończona.
   6. `raport`, a potem podsumowanie dla klienta (5–8 linii, po polsku, prosto): ile wersji zaplanowano, czy hamulec jest włączony, najlepsze wersje z raportu (kandydaci do przepuszczenia do obserwujących w aplikacji Instagram), błędy i alerty, nowa wersja programu (jeśli jest), co pominięto i dlaczego (także wersje pominięte, bo w Zernio jest już inny post na ich termin: podaj ich numery i przepisz podpowiedź programu).

   Gdy coś się nie uda, nie naprawiaj tego na własną rękę. Opisz problem w podsumowaniu.
   ```

5. Uruchamiam zadanie od razu raz, przy kliencie (przyciskiem uruchomienia zadania albo poleceniem w aplikacji, zależnie od wersji), żeby klient zatwierdził „zawsze zezwalaj”. Pierwsza paczka jest już zrobiona, więc to uruchomienie najwyżej dołoży kilka wersji na końcu okna.
6. Zapisuję krok: `bash trial.sh krok --gotowe tydzien --wartosc zadanie` albo `.\trial.cmd krok --gotowe tydzien --wartosc zadanie`. Gdy klient został przy wariancie bez zadania, wartość to `reczny`: `bash trial.sh krok --gotowe tydzien --wartosc reczny` albo `.\trial.cmd krok --gotowe tydzien --wartosc reczny`.

## Jak sprawdzamy

`status` pokazuje wersje na najbliższy tydzień ze statusem „Zaplanowana”, a `krok` nie zgłasza alertu „Na jutro nie ma żadnego triala”. Zadanie jest na liście zadań zaplanowanych w aplikacji, a jego pierwsze uruchomienie zakończyło się podsumowaniem. `krok` pokazuje krok `tydzien` jako gotowy („Zapisane: zadanie.”).

## Gdy nie wychodzi

- Paczka się przerwała albo skończyła błędem (zamknięta aplikacja, uśpiony komputer, limit czasu komendy, gdy ktoś uruchomił ją nie w tle). Uruchom `bash trial.sh paczka --dni 7` albo `.\trial.cmd paczka --dni 7` jeszcze raz, w tle. Pomija zajęte terminy, dokańcza wersje, które nie mają jeszcze posta, i nic nie dubluje.
- `paczka` odmawia: „Paczka czeka na decyzję o pierwszych wersjach: N wersji czeka na akceptację klienta (TR-…).”. Któraś z pierwszych wersji nie została zaakceptowana ani odrzucona. W zadaniu tygodniowym tylko opisz to w podsumowaniu, a decyzję podejmiecie z klientem w rozmowie (patrz krok 8, „Gdy nie wychodzi”).
- Błędy Zernio (kod 401, 402, 429, 5xx). Przeczytaj komunikat: zły klucz, plan, tempo albo chwilowa awaria. Wersja z błędem ma wolny termin. Popraw przyczynę i uruchom `paczka` jeszcze raz (patrz `PULAPKI.md`).
- `paczka` (a z góry także jej plan na sucho) pomija wersje i kończy się wskazówką „Jeśli o tych godzinach publikujesz coś innego, przesuń godziny triali…”: w Zernio jest już inny post klienta na ich termin. Pominięte wersje zostają zaakceptowane, ale ponowne uruchomienie `paczka` ich nie dokończy, bo ten post nadal tam będzie. Postępuj jak w kroku 8 (ostatnie dwa punkty „Gdy nie wychodzi”): zapytaj klienta, za jego zgodą przesuń `hours` (i `brake_slot`), odrzuć pominięte wersje i uruchom `paczka` jeszcze raz. W zadaniu tygodniowym, bez klienta, tylko opisz to w podsumowaniu.
- `paczka` pisze „Uwaga: pomijam rolkę …” (rolka bez hooków albo z hookiem lub podpisem, który łamie limit). To nie blokuje paczki: reszta puli idzie dalej. Opisz to w podsumowaniu, a hooki dopiszecie z klientem w rozmowie (patrz `PULAPKI.md`).
- Komputer przespał niedzielę, więc zadanie się nie wykonało. Przy następnej rozmowie `krok` pokaże alert „Na jutro nie ma żadnego triala”. Zaproponuj paczkę od razu i po „tak” uruchom `paczka --dni 7`.
- Zadania zaplanowane są niedostępne w tej wersji aplikacji. Zostaje wariant bez zadania. W niedzielę klient pisze „zrób paczkę na tydzień”, a ty wykonujesz kroki z promptu po kolei.
- Hamulec jest włączony. Paczka planuje wtedy 1 trial dziennie (o godzinie `brake_slot`), bo zasięg zwykłych rolek wyraźnie spadł. Wyjaśnij to klientowi spokojnie: to zabezpieczenie, nie awaria. Hamulec wyłącza się sam, gdy zasięg wraca, a gdy zwykłych rolek jest za mało, żeby to sprawdzić („za mało danych”), zostaje taki, jaki był.
- Raport albo komenda `hamulec` pisze, że hamulec jest nieaktywny, bo za mało zwykłych rolek (potrzeba co najmniej 5 z 28 dni przed startem triali i 3 z ostatnich dwóch tygodni, każdej z 1000 wyświetleń). To nie awaria: przy rzadkim publikowaniu program nie ma jak policzyć spadku zasięgu, więc klient sam pilnuje, czy triale nie szkodzą zwykłym rolkom (patrz `DLACZEGO.md`).
- Przygotowanie wersji idzie bardzo wolno. Program sam podpowiada mniejszą liczbę triali dziennie. Zmieniasz `daily_max` w `dane/config.json` tylko za zgodą klienta.
- W zadaniu odczyt w Chrome się nie udaje. To nie blokuje paczki: wyniki odczytasz przy najbliższej rozmowie.
