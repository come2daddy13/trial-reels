**Krok 4: Zwycięskie rolki**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Wybieramy do 12 twoich rolek, które przyniosły najwięcej nowych obserwujących. Z nich zrobimy triale.

## Po co

Najlepsza próbna rolka to taka, która już raz się sprawdziła. Zmieniamy w niej tylko opakowanie (napis, emotkę, tempo), a treść zostaje ta, która działa. Liczymy nowych obserwujących, a nie same wyświetlenia, bo wyświetlenia mogą zbierać rolki, po których nikt nie zostaje.

## Co robisz Ty

1. Obejrzyj listę do 25 rolek z największą liczbą wyświetleń, którą ci pokażę. Wykreśl te, które nie pasują: memy, cudze treści, tematy, o których nie chcesz już mówić. Rolki, przy których w kolumnie „Plik” stoi „nie”, nie mają pliku do pobrania w Zernio (zwykle to rolki z muzyką z biblioteki Instagrama), więc zwykle je odpuszczamy.
2. Wybierz sposób odczytu obserwujących z każdej rolki:
   - **Chrome:** odczytam liczby sam z panelu statystyk na Instagramie. Potrzebujesz przeglądarki Chrome, rozszerzenia Claude in Chrome (ze sklepu Chrome) i konta Instagram zalogowanego w tej przeglądarce. Logujesz się sam(a), ja tego nie robię. Jeśli rozszerzenie zapyta o zgodę na dostęp do instagram.com, zdecyduj sam(a).
   - **Ręcznie:** dla każdej rolki przepisujesz z aplikacji Instagram dwie liczby: wyświetlenia i obserwujących z tej rolki. Podpowiem, gdzie je znaleźć. To dłużej, ale bez dodatkowych narzędzi.
3. Potwierdź ostateczną listę.

## Co robię ja

1. Uruchamiam `bash trial.sh kandydaci` albo `.\trial.cmd kandydaci`. Program zapisuje do 25 rolek w `dane/kandydaci.json` i drukuje tabelę (kod, data, wyświetlenia, plik, początek podpisu). Pokazuję ją klientowi czytelnie (nazwa, data, wyświetlenia) i pytam, które wykreślić.
2. Wykreślonych rolek nie usuwam z `dane/kandydaci.json`: to duży plik, a wczytywanie go zjadałoby limit klienta. Zapamiętuję tylko kody rolek, które zostają, i podaję do puli wyłącznie je.
3. Odczytuję obserwujących według opisu „Odczyt liczb z panelu Instagrama” w `SKILL.md` i dla każdej odczytanej rolki zapisuję wynik, podstawiając jej kod i liczby: `bash trial.sh wynik-kandydata Cabc123XYZ_ --wyswietlenia "12,3 tys." --obserwujacy 9` albo `.\trial.cmd wynik-kandydata Cabc123XYZ_ --wyswietlenia "12,3 tys." --obserwujacy 9`. W trybie Chrome odczytuję wszystkie rolki, które zostały na liście. W trybie ręcznym odczytuję 15 rolek z największą liczbą wyświetleń (spośród tych, które zostały) i na tym kończę, chyba że klient chce więcej. Rolki bez odczytu dopełniają pulę według wyświetleń (punkt 4).
4. Wybieram pulę (do 12 rolek), podając kody rolek, które klient zostawił: `bash trial.sh pula KOD1 KOD2 …` albo `.\trial.cmd pula KOD1 KOD2 …`. Zaczynam od rolek z największą liczbą obserwujących (z odczytów, które właśnie zapisałem), a rolki bez odczytu dopełniam według wyświetleń z tabeli. Gdy nie mam żadnego odczytu, mówię klientowi wprost, że wybór według wyświetleń jest słabszą miarą. Komendy `bash trial.sh pula --auto 12` albo `.\trial.cmd pula --auto 12` używam tylko wtedy, gdy klient niczego nie wykreślił: program sam weźmie wtedy rolki z największą liczbą obserwujących. Przy wykreślonych rolkach `--auto` mógłby je dopisać z powrotem.
5. Pokazuję pulę: `bash trial.sh pula` albo `.\trial.cmd pula`.

## Jak sprawdzamy

Komenda `pula` wypisuje rolki i kończy się zdaniem „Rolek w puli: 12 (aktywnych: 12).” (albo mniej, jeśli klient ma mniej dobrych rolek). `krok` pokazuje krok `zwyciezcy` jako gotowy („Aktywnych rolek w puli: N.”). Klient potwierdza listę.

## Gdy nie wychodzi

- „Nie ma rolek, które spełniają warunki.” Konto ma mało rolek albo wszystkie są świeże (program bierze rolki starsze niż 7 dni). Spróbuj dłuższego okresu: `bash trial.sh kandydaci --miesiace 24` albo `.\trial.cmd kandydaci --miesiace 24`, albo wróć za tydzień.
- Klient nie widzi na liście rolki, którą chce dodać. Zwiększ listę: `bash trial.sh kandydaci --ile 50` albo `.\trial.cmd kandydaci --ile 50`. Potem dodaj ją po kodzie z adresu rolki (`instagram.com/reel/KOD/`): `bash trial.sh pula KOD` albo `.\trial.cmd pula KOD`.
- Pula jest mała (np. 3 rolki). To wystarczy. Dziennie pójdzie tyle triali, ile masz aktywnych rolek (np. 3), a żadna rolka nie idzie dwa razy tego samego dnia. Powiedz klientowi, że z czasem warto dodawać nowe zwycięskie rolki.
- Odczyt w Chrome: `login: true` oznacza, że Instagram prosi o logowanie. Poproś klienta, żeby zalogował się sam. Brak liczb: spróbuj jeszcze raz, a potem przejdź na tryb ręczny. Weryfikacja albo ostrzeżenie Instagrama: przerwij i niczego nie klikaj (szczegóły w `SKILL.md`). Brak narzędzi przeglądarki: rozszerzenie jest wyłączone albo niepołączone z aplikacją. Poproś klienta o sprawdzenie, a jeśli się nie uda, wybierz tryb ręczny.
- Wszystkie odczyty to 0 obserwujących. To możliwe: panel liczy tylko obserwujących z tej jednej rolki. Wtedy ranking idzie po wyświetleniach, a ja mówię to klientowi.
- Rozmowa urwała się po odczytach, a przed wyborem puli. Odczyty są zapisane w `dane/kandydaci.json`, ale lista wykreślonych rolek była tylko w rozmowie. Zapytaj klienta jeszcze raz, które rolki zostają, i wybierz pulę tak jak w punkcie 4.
- „Zernio prosi o zwolnienie tempa” (kod 429). Poczekaj minutę i uruchom komendę jeszcze raz.
