**Krok 8: Pierwsze wersje**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Przygotowujemy pierwsze 9 wersji próbnych rolek. Oglądasz je w przeglądarce i akceptujesz te, które mają wyjść.

## Po co

To moment, w którym widzisz, co program zrobi z twoimi rolkami, zanim cokolwiek trafi na Instagram. Po tym kroku kolejne paczki mogą powstawać same, bo wiesz, czego się spodziewać. Pierwsze 9 wersji akceptujesz ty, żeby nic nie wyszło pod twoim nazwiskiem bez twojej zgody.

## Co robisz Ty

1. Poczekaj, aż przygotuję wersje (kilka minut, zależnie od komputera). Potem otworzy się strona z wersjami w przeglądarce.
2. Obejrzyj każdą wersję: wideo, napis z hookiem, podpis i opis zmian. Sprawdź, czy napis jest czytelny, czy niczego nie zasłania, czy podpis brzmi jak ty i czy nie ma w nim niczego, czego nie chcesz pokazać.
3. Powiedz, które wersje odrzucasz (numery TR-…). Możesz podać powód, ale nie musisz. Zrobię w ich miejsce nowe.
4. Gdy jesteś zadowolony(-a), powiedz wyraźnie „akceptuję”: wszystkie wersje albo wskazane numery.
5. Zanim wyślę wersje do Zernio, pokażę ci terminy i zapytam o ostatnie „tak”. Od tej chwili posty czekają w Zernio na publikację. Możesz je usunąć w panelu Zernio.

## Co robię ja

1. Uruchamiam `bash trial.sh pierwsze` albo `.\trial.cmd pierwsze` w tle. Komenda przygotowuje 9 wersji, bez wysyłki do Zernio, i otwiera podgląd. Jeśli wypisze podpowiedź o czasie przygotowania wersji, przekazuję ją klientowi prostymi słowami i pytam o decyzję (ustawienie `daily_max` w `dane/config.json`).
2. Jeśli podgląd się nie otworzył, otwieram `dane/podglad.html` (Mac: `open dane/podglad.html`, Windows w PowerShellu: `Start-Process dane\podglad.html`, w Git Bash: `explorer "dane\podglad.html"`). Strona musi zostać w folderze `dane`, bo filmy ma obok, w `dane/wersje`.
3. Dla odrzuconych wersji uruchamiam `bash trial.sh odrzuc TR-003 --powod "hook zasłania twarz"` albo `.\trial.cmd odrzuc TR-003 --powod "hook zasłania twarz"` (numer i powód podstawiam swoje). Jeśli powodem jest hook, poprawiam go albo usuwam z `dane/hooki.json`, zanim ruszę dalej, bo inaczej program może wylosować go ponownie. Potem `bash trial.sh pierwsze` albo `.\trial.cmd pierwsze` jeszcze raz: dorobi tyle wersji, ile brakuje do 9.
4. Po wyraźnym „akceptuję” uruchamiam `bash trial.sh akceptuj --wszystkie` albo `.\trial.cmd akceptuj --wszystkie`. Dla wskazanych wersji: `bash trial.sh akceptuj TR-001 TR-002` albo `.\trial.cmd akceptuj TR-001 TR-002`. Program kończy tę komendę zdaniem „Następny krok to zaplanuj, ale dopiero po wyraźnej zgodzie klienta na pokazane terminy …”. To tylko wskazanie kolejnego kroku, a nie zgoda na planowanie, więc nie planuję od razu: idę do punktu 5.
5. Próba na sucho: `bash trial.sh zaplanuj --na-sucho` albo `.\trial.cmd zaplanuj --na-sucho`. Pokazuje, ile wersji zostanie zaplanowanych, niczego nie wysyła. Terminy pokazuję klientowi z komendy `status` (`bash trial.sh status` albo `.\trial.cmd status`), w jego czasie, i pytam o ostatnie „tak”. Jeśli komenda pisze, że pomija wersje, bo w Zernio jest już inny post na ten termin (patrz ostatnie dwa punkty „Gdy nie wychodzi”), najpierw to poprawiamy. Gdy pomija tylko część wersji, klient może zdecydować, że reszta idzie od razu po jego „tak”.
6. Po „tak” uruchamiam `bash trial.sh zaplanuj` albo `.\trial.cmd zaplanuj`. Planuje zaakceptowane wersje w Zernio jako triale MANUAL, wyłącznie w oknie publikacji.

## Jak sprawdzamy

`status` pokazuje 9 wersji ze statusem „Zaplanowana”. `krok` pokazuje krok `pierwsze` jako gotowy („Zaplanowanych albo opublikowanych wersji: N.”). Klient może zajrzeć do panelu Zernio: zaplanowane posty na Instagramie powinny tam być widoczne.

## Gdy nie wychodzi

- „Nie udało się zrobić wersji…”. Komunikat podaje powód, najczęściej fraza z `strong` albo `cuts` nie pasuje do transkrypcji albo brakuje pliku rolki. Napraw przyczynę i uruchom `pierwsze` jeszcze raz. Terminy nieudanych wersji są znów wolne.
- Podgląd się nie otwiera albo filmy się nie odtwarzają. Otwórz `dane/podglad.html` ręcznie w przeglądarce (punkt 2).
- Klient odrzuca prawie wszystko. Zapytaj, co mu nie pasuje: hook, podpis czy zmiany montażowe. Zmień ustawienia rolek (krok 6) albo hooki (krok 7), odrzuć pozostałe wersje i uruchom `pierwsze` jeszcze raz.
- Klient chce zmienić hook jednej wersji. Gotowej wersji nie edytujemy. Odrzucamy ją, poprawiamy hook w `dane/hooki.json` i robimy nową.
- `zaplanuj` zgłasza błąd Zernio (kod 401, 402, 429 albo 5xx). Przeczytaj komunikat: zły klucz, plan, tempo albo chwilowa awaria. Napraw przyczynę lub poczekaj kilka minut i uruchom `zaplanuj` jeszcze raz. Co już poszło, zostaje.
- `paczka` odmawia: „Paczka czeka na decyzję o pierwszych wersjach: N wersji czeka na akceptację klienta (TR-…).”. Klient zaakceptował i zaplanował tylko część pierwszych wersji, a reszty nie obejrzał. Poproś go, żeby obejrzał podgląd (`podglad`) i wyraźnie napisał „akceptuję” albo wskazał wersje do odrzucenia, a dopiero wtedy uruchom `akceptuj` albo `odrzuc`. Potem paczka ruszy. Plan na sucho (`paczka --na-sucho`) pokazuje wtedy plan i mówi, że prawdziwa paczka czeka na tę decyzję.
- Oglądanie trwało długo i terminy minęły. Program przesuwa takie wersje na najbliższe wolne terminy w oknie publikacji. To normalne.
- Klient chce wycofać zaplanowaną wersję. Komenda `odrzuc` nie usuwa postów z Zernio. Post usuwa się w panelu Zernio.
- `zaplanuj` (także z `--na-sucho`) pisze dla pominiętych wersji: „TR-001: na RRRR-MM-DD GG:MM masz już inny post na Instagramie. Pomijam tę wersję.”, a na końcu „Na sucho: zaplanowałbym 0 z 9. Nic nie wysłałem i nic nie zmieniłem.” (bez `--na-sucho`: „Zaplanowane w Zernio: 0 z 9.”). To nie awaria. W Zernio na to konto czeka już inny post na dokładnie tę minutę (klient publikuje coś o tych godzinach, także z innego narzędzia), a program nie planuje dwóch postów naraz. Program podpowiada: „Jeśli o tych godzinach publikujesz coś innego, przesuń godziny triali w ustawieniach (pole hours w dane/config.json, np. na 09:05–21:05), odrzuć pominięte wersje (odrzuc TR-001) i zrób nowe komendą pierwsze albo paczka.” Postępuj po kolei: (1) zapytaj klienta, czy o tych godzinach publikuje coś innego; (2) za jego zgodą zmień w `dane/config.json` pole `hours` na godziny, które nie zbiegają się z jego postami (np. `["09:05", "21:05"]`), a razem z nim `brake_slot` (domyślnie `"13:00"`, np. na `"13:05"`), bo o tej godzinie idzie jedyny trial dziennie, gdy włączy się hamulec; (3) odrzuć pominięte wersje komendą `odrzuc` z numerami z podpowiedzi i zrób nowe komendą `pierwsze` (przy paczce tygodniowej `paczka`); (4) dalej jak zwykle: podgląd, „akceptuję”, `zaplanuj`. Samo przesunięcie godzin nie wystarczy, bo wersja zachowuje swój termin: trzeba ją odrzucić i zrobić nową.
- Klient niczego innego o tych godzinach nie publikuje, a w panelu Zernio stoi post, który wygląda jak wersja z tego programu (ten sam hook i podpis). To pozostałość po przerwanym planowaniu. Poproś klienta o usunięcie tego posta w panelu Zernio i uruchom `zaplanuj` jeszcze raz.
