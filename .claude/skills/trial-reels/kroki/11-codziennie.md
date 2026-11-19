**Krok 11: Na co dzień**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Omawiamy, jak wygląda praca z programem na co dzień: jak przepuścić udany trial do obserwujących, jak czytać raport i kiedy aktualizować program.

## Po co

Konfiguracja jest za nami i program robi większość pracy sam. Zostają trzy rzeczy, które robisz ty: wybierasz, co pokazać obserwującym, czytasz raport i od czasu do czasu zgadzasz się na aktualizację. Wolę, żebyś wiedział(a), jak je robić, zanim będą potrzebne.

## Co robisz Ty

1. **Udany trial do obserwujących.** Raz w tygodniu dostajesz raport z listą najlepszych wersji. Jeśli któraś ci się podoba, możesz pokazać ją swoim obserwującym. Robisz to sam(a), w aplikacji Instagram na telefonie: wejdź na swój profil, do rolek, znajdź próbne rolki, otwórz wybraną (poznasz ją po dacie i napisie z hookiem, które ci podam) i poszukaj przycisku do udostępnienia obserwującym. Nazwy w aplikacji zależą od wersji. Jeśli ich nie widzisz, opisz mi albo wyślij zrzut ekranu. Zwykle wybieraj jedną wersję na rolkę, żeby obserwujący nie widzieli tej samej rolki kilka razy.
2. **Raport.** Raz w tygodniu dostajesz krótkie podsumowanie. Przeczytanie go zajmuje ok. 2 minut. Wyjaśnię ci każdą liczbę, jeśli zapytasz.
3. **Aktualizacje.** Gdy będzie nowa wersja programu, powiem ci, co się zmieniło. Aktualizujemy tylko za twoją zgodą. Twoje dane zostają nietknięte.
4. **Gdy chcesz coś zmienić:** dodać nową rolkę do puli, zmniejszyć liczbę triali dziennie, wstrzymać paczki albo przestać z programu korzystać. Wystarczy mi powiedzieć.

## Co robię ja

1. **Jak czytać raport.** Komenda `raport` zapisuje plik w `dane/raporty/` i pokazuje go: `bash trial.sh raport` albo `.\trial.cmd raport`. Tłumaczę klientowi:
   - „Hamulec” mówi, czy program ograniczył triale do 1 dziennie, bo zasięg zwykłych rolek wyraźnie spadł.
   - Tabela pokazuje dla każdej rolki: ile miała triali, ile zmierzonych, sumę wyświetleń i nowych obserwujących, wynik „Obs./1000” (nowi obserwujący na 1000 wyświetleń) i „Wagę”. Waga 2 znaczy, że rolka wychodzi częściej, a 0,5, że rzadziej (po zmierzeniu co najmniej 6 rolek).
   - „Najlepsze wersje” to kandydaci do pokazania obserwującym. Adres triala jest w nawiasie na końcu linii, gdy wersja jest już opublikowana. Wersja zmierzona ręcznie, a jeszcze nieopublikowana, ma samą linię z wynikiem, bez nawiasu.
   - „Błędy” to wersje, których nie udało się zaplanować albo opublikować, z powodem.
   - „Bank hooków prawie pusty” to nie problem: idą wtedy powtórki najlepszych hooków. Na start piszemy po 5 hooków na rolkę, więc ten komunikat pojawia się zwykle już po pierwszym tygodniu (po prawdziwej paczce, a także w planie na sucho, który liczy bank z góry). Gdy klient ma ochotę, dopiszcie razem po kilka nowych hooków na osobnym posiedzeniu (zasady jak w kroku 7). To nie jest pilne.
2. **Przepuszczanie.** Podaję klientowi numer wersji, rolkę, termin i hook (z komendy `status --wszystkie`, bo samo `status` pokazuje tylko ostatnie 14 dni, albo z raportu), żeby znalazł próbną rolkę w aplikacji. Nie robię tego za niego, bo wymaga to jego konta w aplikacji Instagram.
3. **Nowa rolka w puli.** Gdy klient opublikuje nową dobrą rolkę (albo chce dodać inną): `bash trial.sh kandydaci` albo `.\trial.cmd kandydaci`, potem `bash trial.sh pula KOD` albo `.\trial.cmd pula KOD` z kodem rolki. Następnie robimy dla niej kroki 5, 6 i 7 (pliki, ustawienia, hooki). `krok` sam wskaże, czego brakuje. Dokańczam to w tej samej rozmowie, zanim ruszy następna paczka. Rolka bez hooków nie blokuje paczki: program pomija ją z ostrzeżeniem („Uwaga: pomijam rolkę …”), a `krok` pokazuje alert „Rolka … nie ma hooków …” (patrz `PULAPKI.md`). Rolka z hookami, ale bez pliku albo transkrypcji, dałaby wersje z błędem, więc gdy nie zdążymy dokończyć kroków 5, 6 i 7, ustawiam nowej rolce `"active": false` do czasu ich zakończenia, żeby zadanie tygodniowe nie próbowało jej przygotowywać bez pliku.
4. **Aktualizacja.** Postępuj według „Aktualizacja” w `SKILL.md`: `bash trial.sh aktualizuj` albo `.\trial.cmd aktualizuj` pokazuje zmiany, a po wyraźnym „tak” klienta `bash trial.sh aktualizuj --tak` albo `.\trial.cmd aktualizuj --tak`. Aplikacja jeszcze raz zapyta o zgodę na tę komendę, więc uprzedzam o tym klienta. Nie aktualizuję, gdy w tle działa `paczka` albo `pierwsze`.
5. **Zmniejszenie liczby triali, zmiana godzin, wstrzymanie.** Zmieniam `daily_max`, `hours` albo `day_window` w `dane/config.json` tylko na prośbę klienta. Wstrzymanie paczek to wyłączenie zadania tygodniowego w aplikacji. Zaplanowane już posty zostają w Zernio, dopóki klient ich tam nie usunie.
6. **Przerwa albo koniec.** Gdy klient chce przestać: usuwa zaplanowane posty w panelu Zernio, wyłącza zadanie tygodniowe w aplikacji i może usunąć folder (dane są tylko u niego).
7. Gdy klient potwierdzi, że wie, jak pracować na co dzień, zapisuję krok: `bash trial.sh krok --gotowe codziennie` albo `.\trial.cmd krok --gotowe codziennie`.

## Jak sprawdzamy

Klient potrafi własnymi słowami powiedzieć, co robi w niedzielę (nic, zadanie robi to samo), jak wybrać wersję do pokazania obserwującym i że aktualizacja wymaga jego „tak”. `krok` pokazuje krok `codziennie` jako gotowy („Zasady na co dzień omówione.”), a `nastepny` ma wartość `null`.

## Gdy nie wychodzi

- Klient nie znajduje próbnych rolek w aplikacji. Poproś o opis ekranu albo zrzut. Próbne rolki nie pojawiają się w siatce profilu, więc szuka się ich w zakładce rolek albo w panelu profesjonalnym. Nie wymyślaj nazw menu: pytaj, co klient widzi.
- Klient nie wie, którą wersję wybrać. Wskaż tę z największą liczbą nowych obserwujących na 1000 wyświetleń, ale zaznacz, że mała liczba wyświetleń to słaby dowód. Decyzja należy do niego.
- Raport jest pusty albo pokazuje same zera. Wyniki odczytujemy dopiero od 3. dnia po publikacji i dopiero po pierwszym odczycie (krok 9). Wyjaśnij to i uruchom odczyt.
- Klient pyta, czy to „zepsuje” jego konto. Nie składaj obietnic w żadną stronę. Wyjaśnij, jak działa hamulec i że może w każdej chwili zmniejszyć liczbę triali albo je wstrzymać.
- Pojawia się alert z `krok` (brak triali na jutro, wersje z błędem, rolka bez hooków, nowa wersja programu). Postępuj według sekcji „Alerty z komendy krok” w `SKILL.md`.
