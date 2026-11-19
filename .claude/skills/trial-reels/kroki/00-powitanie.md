**Krok 0: Powitanie**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Poznajemy się z programem: mówię ci, czym są trial reels, co zrobimy razem i ile to potrwa.

## Po co

Zanim cokolwiek zainstalujemy, chcesz wiedzieć, na co się zgadzasz: co program robi z twoim kontem, ile to zajmie i czego potrzebujesz. Dzięki temu nic cię nie zaskoczy.

## Co robisz Ty

1. Przeczytaj krótkie wyjaśnienie, które ci powiem:
   - Trial reel (próbna rolka) to rolka, którą Instagram pokazuje tylko ludziom, którzy cię jeszcze nie obserwują. Nie ma jej w siatce na twoim profilu i nie widzą jej twoi obserwujący.
   - Program bierze twoje najlepsze rolki, które już raz się sprawdziły, robi z nich drobne wersje (inny napis na początku, emotka, lekkie przybliżenie) i planuje je w Zernio jako triale. Domyślnie do 10 dziennie.
   - Raz w tygodniu program liczy, które rolki przyciągają najwięcej nowych obserwujących, i według tego układa kolejne wersje.
   - O wszystkim, co wychodzi, decydujesz ty. Pierwsze 9 wersji oglądasz i akceptujesz sam(a). Udany trial pokazujesz obserwującym sam(a), w aplikacji Instagram.
   - Niczego nie obiecuję. Sprawdzimy w liczbach, co u ciebie działa.
2. Sprawdź, czy masz:
   - konto na Instagramie firmowe albo twórcy (nie osobiste),
   - komputer z Macem (macOS 12 lub nowszy) albo z Windowsem 10 lub 11 na procesorze x64 (Windows na procesorze ARM nie jest obsługiwany, bo brakuje dla niego pakietów),
   - co najmniej 5 GB wolnego miejsca na dysku (sam model rozpoznawania mowy to ok. 1,6 GB, a paczka wersji na tydzień kolejne ok. 1,3 GB; przy 10 wersjach dziennie pliki wersji z czasem zajmują kilka GB, bo program kasuje je 14 dni po publikacji, więc zostaw zapas),
   - najlepiej 8 GB pamięci RAM lub więcej (to zalecenie, program go nie sprawdza; przy mniejszej ilości przygotowanie wersji może być bardzo wolne),
   - 60–90 minut. Możemy to zrobić w dwóch podejściach, bo postęp zapisuje się w plikach,
   - przeglądarkę Chrome, jeśli chcesz, żebym odczytywał wyniki z Instagrama sam. Bez niej też się da, ręcznie.
3. Aplikacja będzie prosić o zgodę na komendy. Przed każdą powiem, co robi. Opcja „zawsze zezwalaj” zmniejsza liczbę pytań. Jeśli aplikacja zapyta, czy ufasz temu folderowi, zgódź się: to twój własny folder z programem.
4. Napisz „dalej”, gdy chcesz zaczynać.

## Co robię ja

1. Jeśli istnieje `.venv`, uruchamiam komendę `krok`: `bash trial.sh krok` albo `.\trial.cmd krok`. Na świeżej instalacji `.venv` jeszcze nie ma, więc tego nie robię.
2. Pytam, jakie konto na Instagramie ma klient. Jeśli osobiste, pokazuję, jak przełączyć je na profesjonalne (Twórca albo Firma): w aplikacji Instagram w ustawieniach, w części o typie konta i narzędziach. Nazwy menu zależą od wersji aplikacji, więc w razie wątpliwości proszę o opis albo zrzut ekranu.
3. Tłumaczę punkty z sekcji „Co robisz Ty” własnymi słowami i czekam na „dalej”.
4. Zapisu kroku nie robię od razu, bo na świeżej instalacji nie ma jeszcze środowiska programu. Robię go zaraz po kroku 1 (Programy): `bash trial.sh krok --gotowe powitanie` albo `.\trial.cmd krok --gotowe powitanie`. Jeśli środowisko już jest (klient wrócił po przerwie), zapisuję od razu.
5. Przechodzę do kroku 1.

## Jak sprawdzamy

Klient napisał „dalej”, a wiem, jakie ma konto na Instagramie i ile ma miejsca na dysku (dokładnie sprawdzi to `doktor` w kroku 1). Po zapisie `krok` pokazuje krok `powitanie` jako gotowy: „Powitanie za nami.”

## Gdy nie wychodzi

- Klient ma konto osobiste. Przełączenie na profesjonalne jest bezpłatne i można je cofnąć w tych samych ustawieniach. Bez konta profesjonalnego triale i połączenie z Zernio nie zadziałają, więc to trzeba załatwić przed krokiem 2.
- Klient ma wątpliwości (co się stanie z moim kontem?). Wróć do głównych zasad: o wszystkim decyduje on, pierwsze 9 wersji akceptuje sam, udany trial puszcza do obserwujących sam, a zaplanowane posty może w każdej chwili usunąć w panelu Zernio. Zachęć do pytań i w razie potrzeby sięgnij do `DLACZEGO.md`.
- Klient nie chce Chrome ani rozszerzenia. To w porządku: wyniki odczytujemy ręcznie (krok 9).
- Klient ma mało miejsca na dysku. `doktor` w kroku 1 sprawdzi dokładnie, a zwolnienie miejsca zajmuje kilka minut. Można zacząć później.
- Aplikacja co chwilę pyta o zgodę. Wyjaśnij, że to jej zabezpieczenie, a wybór „zawsze zezwalaj” zmniejsza liczbę pytań.
