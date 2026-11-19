# Pułapki i co z nimi robić

Zajrzyj tu, gdy coś nie działa albo wynik komendy cię zaskakuje. Każda pułapka ma objaw, przyczynę i to, co robisz. Klientowi tłumacz spokojnie i krótko. Większość z tych rzeczy to normalne trudności, a nie wina klienta.

## Muzyka z biblioteki Instagrama

**Objaw:** `pobierz` pisze „Zernio nie ma jej pliku”. Rolka dostaje `brak_pliku: true`, a krok `pliki` nie chce się zamknąć.

**Przyczyna:** rolki z muzyką wybraną z biblioteki Instagrama nie mają w Zernio pliku wideo.

**Co robisz:** zapytaj klienta, czy ma oryginał tej rolki (z telefonu albo z edytora). Jeśli tak, otwórz mu folder `dane/src` (polecenia do tego są w kroku 5), niech wrzuci plik pod nazwą `KOD.mp4` (kod rolki, rozszerzenie `mp4`). Wersje wyjdą wtedy bez muzyki z biblioteki, więc rolka może działać inaczej niż oryginał. Najczęściej lepiej ją pominąć: ustaw `"active": false` w `dane/pula.json` i dopisz zastępstwo, czyli kod kolejnej rolki, którą klient zostawił na liście kandydatów (`pula KOD`). `pula --auto 12` jest dobre tylko wtedy, gdy klient niczego z listy nie wykreślał, bo `--auto` mogłoby dopisać z powrotem rolki, które wykreślił.

## Cudze dane na ekranie (`blur`)

**Objaw:** w rolce widać cudze nazwiska, adresy e-mail, numery telefonów albo wiadomości od klientów.

**Przyczyna:** próbne wersje idą w kilkunastu odmianach, więc cudze dane powielałyby się wszędzie.

**Co robisz:** zanim rolka stanie się aktywna, ustaw `blur` w `dane/pula.json` (przedział czasu `t` w sekundach i `box` jako ułamki kadru). Program robi raz kopię źródła z rozmyciem (`dane/src/KOD.blur-….mp4`), a zmiana `blur` robi nową kopię. Sprawdź efekt komendą `kadr KOD --t SEKUNDA` w chwili, gdy dane są widoczne: klatka uwzględnia rozmycie. Nową rolkę z cudzymi danymi dodawaj od razu z `"active": false`, ustaw `blur` i dopiero potem włącz.

## Wypalone napisy (`mask`, `hook_y`)

**Objaw:** hook zasłania napis wypalony w nagraniu albo twarz.

**Przyczyna:** hook to biały dymek, który przez pierwsze ok. 3 sekundy leży w stałym miejscu kadru (domyślnie blisko góry).

**Co robisz:** przesuń dymek polem `hook_y`. Jeśli stary napis trwa dłużej niż 3 sekundy albo jest przez całą rolkę, użyj `mask`: dymek zostaje wtedy do końca rolki i zasłania napis (`y` to jego pozycja, `min_w` i `min_h` to minimalny rozmiar). Gdy nad głową prowadzącego nie ma miejsca, zwiększ `hook_y`. Sprawdzaj komendą `kadr` w kilku momentach.

## Whisper tnie słowa z łącznikiem (np. „e-mail”)

**Objaw:** `sprawdz-pule` albo `pierwsze` pisze, że frazy z `strong` albo `cuts` „nie ma w transkrypcji”, choć klient ją wypowiada.

**Przyczyna:** rozpoznawanie mowy zapisuje niektóre słowa inaczej, niż się je wypowiada: tnie słowa z łącznikiem na kawałki (np. „e” i „-mail”), a liczby, skróty i nazwy własne zapisuje po swojemu.

**Co robisz:** frazę zawsze kopiuj dosłownie z `dane/transkrypcje/KOD.json`. Program porównuje same litery (bez spacji, łączników, interpunkcji i wielkości liter), więc różnice w takich drobiazgach nie szkodzą. Szkodzi inne słowo, inna liczba albo inny skrót. Gdy fraza nadal nie pasuje, wybierz inny fragment zdania.

## Rolka bez mowy

**Objaw:** `sprawdz-pule` dopisuje po wyniku linię w rodzaju „Informacja: Rolka NAZWA (KOD): rolka bez mowy (transkrypcja ma 0 słów), więc nie potrzebuje pól strong ani cuts. Poziom zmian Mocna jej nie dotyczy, bo nie ma zdania na zimne otwarcie.” W `dane/transkrypcje/KOD.json` nie ma żadnego słowa.

**Przyczyna:** w rolce nikt nie mówi (sama muzyka, napisy na ekranie), więc nie ma czego zapisać. Program odcina muzykę i ciszę, żeby rozpoznawanie mowy nie wymyślało zdań tam, gdzie nikt nie mówi.

**Co robisz:** to nie błąd. Zapytaj klienta, czy rolkę zostawiamy. Zostaje: hooki i podpis układasz z jej podpisu (`caption`) i z obrazu (klatki z `kadr`, napisy na ekranie), `strong` i `cuts` zostają puste, a transkrypcji nie cytujesz (jest pusta). Taka rolka dostaje tylko wersje Subtelną i Średnią. Nie zostaje: ustaw `"active": false` i dopisz zastępstwo (patrz „Muzyka z biblioteki Instagrama”). Gdy rolka bez mowy ma ustawione `strong` albo `cuts`, `sprawdz-pule` zgłasza problem: „Rolka NAZWA (KOD): rolka nie ma mowy (transkrypcja ma 0 słów), więc pola strong i cuts nie mają sensu. Usuń je z dane/pula.json.” Usuń wtedy oba pola z tej rolki.

**Zmyślona transkrypcja:** transkrypcje zrobione bez filtra głosu (starsze wersje programu) potrafiły mieć w rolce bez mowy zmyślone zdania, np. „Dzięki za oglądanie!”, zdanie po angielsku albo samo „KONIEC”. Program nie rozpozna takiej rolki jako rolki bez mowy, więc `sprawdz-pule` nie napisze o niej „Informacja:”. Nie cytuj tych zdań. Za zgodą klienta usuń `dane/transkrypcje/KOD.json` i uruchom `transkrybuj` jeszcze raz: rolka dostanie pustą transkrypcję.

## W Zernio jest już inny post na ten termin

**Objaw:** `zaplanuj` albo `paczka` pisze „TR-001: na RRRR-MM-DD GG:MM masz już inny post na Instagramie. Pomijam tę wersję.”, a `zaplanuj --na-sucho` kończy się zdaniem „Na sucho: zaplanowałbym 0 z 9. Nic nie wysłałem i nic nie zmieniłem.” (bez `--na-sucho`: „Zaplanowane w Zernio: 0 z 9.”). Pod spodem jest wskazówka „Jeśli o tych godzinach publikujesz coś innego, przesuń godziny triali w ustawieniach (pole hours w dane/config.json, np. na 09:05–21:05), odrzuć pominięte wersje (odrzuc TR-001) i zrób nowe komendą pierwsze albo paczka.”

**Przyczyna:** w Zernio na to konto czeka już post na dokładnie tę minutę: własny post klienta, post z innego narzędzia albo pozostałość po przerwanym planowaniu. Program nie planuje dwóch postów na tę samą minutę.

**Co robisz:** to nie awaria. Kolejność jest w kroku 8 (`kroki/08-pierwsze.md`, ostatnie dwa punkty „Gdy nie wychodzi”): zapytaj klienta, za jego zgodą przesuń pole `hours` (a z nim `brake_slot`, np. na 13:05, bo domyślne 13:00 to też pełna godzina), odrzuć pominięte wersje i zrób nowe. Samo przesunięcie godzin nie wystarczy, bo wersja zachowuje swój termin. W zadaniu tygodniowym niczego nie przestawiaj, tylko opisz to w podsumowaniu. Pominięte wersje zostają „zaakceptowane”, a ponowne uruchomienie `paczka` ich nie dokończy, bo ten post nadal tam stoi.

**Plan na sucho ostrzega z góry.** `paczka --na-sucho` i `zaplanuj --na-sucho` pytają Zernio o zajęte terminy tym samym sprawdzeniem co prawdziwe planowanie (tylko odczyt: niczego nie wysyłają, nie renderują i nie zmieniają). Przy `paczka --na-sucho` wersji jeszcze nie ma, więc linia brzmi „! RRRR-MM-DD GG:MM (nazwa rolki): na ten termin masz już inny post na Instagramie. Pomijam ten termin.”, po niej idzie „Na sucho: zaplanowałbym X z Y. Nic nie wysłałem i nic nie zmieniłem.”, a wskazówka kończy się na przesunięciu godzin: „Jeśli o tych godzinach publikujesz coś innego, przesuń godziny triali w ustawieniach (pole hours w dane/config.json, np. na 09:05–21:05) i uruchom plan na sucho jeszcze raz.” Nie ma wtedy czego odrzucać. Gdy po pierwszym zaplanowaniu czekają zaakceptowane wersje bez posta, plan na sucho zaczyna od „Dokończyłbym zaakceptowane wersje, które nie trafiły jeszcze do Zernio: N.” i pokazuje ich pominięcia z numerami do odrzucenia, tak jak zrobiłaby prawdziwa paczka.

## Rolka bez hooków albo z hookiem, który łamie limit

**Objaw:** `paczka` (także `pierwsze` i plan `paczka --na-sucho`) pisze „Uwaga: pomijam rolkę NAZWA (KOD): nie ma hooków w dane/hooki.json (dopisz co najmniej 3). Reszta puli idzie dalej. Popraw to i uruchom sprawdz-pule: rolka wróci do planu od następnej paczki.” Zamiast braku hooków powodem bywa hook albo podpis, który łamie limit, na przykład „hook h02: tekst ma 51 znaków, a limit to 50”. Gdy nie zostaje żadna rolka do planu, komenda kończy się komunikatem „Nie ma rolki, z której da się zrobić wersje.” i kodem 1. `krok` pokazuje wtedy alert „Rolka NAZWA (KOD) nie ma hooków w dane/hooki.json, więc paczka ją pomija. …”.

**Przyczyna:** rolkę dodano do puli (komenda `pula`), a hooków jeszcze nikt nie napisał, albo hooki dopisane później łamią limity (hook do 50 znaków, emotka z zestawu, podpis do 2200 znaków). Plan sam sprawdza to, co psułoby wersje, i pomija taką rolkę zamiast zatrzymywać całą paczkę.

**Co robisz:** to nie awaria. Reszta puli idzie dalej, a pominięta rolka po prostu nie dostaje nowych wersji. Dokończ dla niej kroki 5–7 (`kroki/11-codziennie.md`): hooki według zasad z `SKILL.md`, potem `sprawdz-pule`. Rolka wróci do planu od następnej paczki. W zadaniu tygodniowym niczego nie dopisuj na własną rękę, tylko opisz to w podsumowaniu.

## Chwilowe błędy Zernio (502 i podobne)

**Objaw:** komunikat „Zernio ma chwilową awarię (kod 502)”, „kod 503” albo „prosi o zwolnienie tempa (kod 429)”. Zdarza się przy wysyłce plików.

**Przyczyna:** usługa jest chwilowo przeciążona albo ogranicza tempo.

**Co robisz:** program sam próbuje wysłać plik do 4 razy, z przerwami między próbami. Jeśli mimo to komenda się zakończy błędem, poczekaj kilka minut i uruchom ją jeszcze raz. Wersja ze statusem „Błąd” ma wolny termin: popraw przyczynę i uruchom `paczka` jeszcze raz (zrobi nową wersję na ten termin) albo odrzuć ją komendą `odrzuc ID`. Kody 401 i 403 to zły klucz (patrz krok 2), a 402 to plan w Zernio.

## Plik w katalogu tymczasowym Zernio żyje 7 dni

**Objaw:** wersja czeka zaakceptowana, bez posta, dłużej niż tydzień (np. po przerwanej paczce).

**Przyczyna:** plik wgrany do Zernio leży w jego katalogu tymczasowym (`temp/`) 7 dni i staje się stały dopiero przy tworzeniu posta.

**Co robisz:** nic. Gdy plik ma ponad 6 dni, `zaplanuj` albo `paczka` same wgrają go jeszcze raz. Nie planuj niczego ręcznie w Zernio na podstawie samego wgranego pliku.

## Panel statystyk Instagrama: jak czytać liczby

- „Wyświetlenia” w panelu to wyświetlenia na Instagramie i na Facebooku razem.
- „Udostępnienia” bywa zawsze 0, a „Widzowie” (podział na obserwujących i nieobserwujących) bywa niewiarygodny. Nie wyciągaj z nich wniosków. Zakładka „Wszystko” wystarcza, bo trial nie ma reklam.
- Techniczna flaga rolki `is_revealed` po kilkunastu godzinach zmienia się na `true`. To NIE znaczy, że trial poszedł do obserwujących. Trial widzą nadal głównie osoby, które klienta nie obserwują, i nie ma go w siatce profilu.
- Obserwujących z rolki nie zwraca Zernio (pole `follows` jest dla rolek zawsze zerem) ani API Mety. Dlatego czytamy ich z panelu, w Chrome albo ręcznie.

## Folder w iCloud albo OneDrive

**Objaw:** `doktor` pisze ✗ „Folder poza iCloud i OneDrive”. Instalacja się wiesza, pliki „znikają” albo render jest bardzo wolny.

**Przyczyna:** synchronizacja z chmurą trzyma część plików tylko w chmurze (są niepobrane) i blokuje środowisko programu. Na Macu synchronizacja Pulpitu i Dokumentów w iCloud nie zmienia widocznej ścieżki, a na Windowsie OneDrive często synchronizuje Dokumenty i Pulpit.

**Co robisz:** poproś klienta o przeniesienie całego folderu `trial-reels` do katalogu domowego (Mac: Finder, Idź, Katalog domowy. Windows: `C:\Users\<ty>`) i o ponowne otwarcie w aplikacji Claude. `.venv` zrób od nowa: usuń go (to tylko zainstalowane programy) i powtórz instalację z kroku 1. Ścieżki z polskimi literami i spacją są w porządku.

## Aktualizacja przerwana w połowie

**Objaw:** po aktualizacji przerwanej twardo (wyłączony albo uśpiony komputer, brak prądu, zamknięte okno w trakcie) program się nie uruchamia, `wersja` pokazuje starą wersję albo `doktor` zgłasza dziwne błędy.

**Przyczyna:** aktualizacja sama cofa zmiany przy błędzie i przy Ctrl+C, ale twarde przerwanie może zostawić mieszankę starych i nowych plików programu.

**Co robisz:** najpierw uruchom `aktualizuj --tak` jeszcze raz (po zgodzie klienta): zwykle dokończy przerwaną aktualizację. Gdy to nie pomaga albo sam program się nie uruchamia, za zgodą klienta pobierz zip najnowszego wydania i rozpakuj go na folder programu tak samo jak przy instalacji (`README.md`, „Część dla Claude”, punkt 2). Folderów `dane/` i `.venv` zip nie zawiera, więc dane klienta i zainstalowane programy zostają. Potem uruchom `doktor`.

## Przerwana paczka

**Objaw:** `paczka` albo `pierwsze` zatrzymały się w trakcie (limit czasu komendy, zamknięta aplikacja, uśpiony komputer, Ctrl+C).

**Co robisz:** uruchom tę samą komendę jeszcze raz. Stan zapisuje się po każdej wersji, więc program pomija zajęte terminy, dokańcza wersje bez posta i niczego nie dubluje. Po trzech błędach z rzędu paczka przerywa się z komunikatem, a po błędzie klucza, płatności, limitu, awarii Zernio albo braku internetu przerywa od razu. W zadaniu tygodniowym ponawiasz (też w tle) najwyżej 3 razy, a potem opisujesz problem w podsumowaniu.

## Komputer przespał niedzielę

**Objaw:** `krok` pokazuje alert „Na jutro nie ma żadnego triala”.

**Co robisz:** zaproponuj klientowi paczkę od razu i po „tak” uruchom `paczka --dni 7`. Jest bezpieczna po przerwie.

## Strefa czasowa i okno publikacji

**Objaw:** komenda pisze „Nieznana strefa czasowa „X” w dane/config.json. Otwórz ten plik i w polu timezone wpisz nazwę w formie Europe/Warsaw albo usuń z pliku wiersz timezone.” (kod wyjścia 2) albo ustawienie z `dane/config.json` jest odrzucane. Przy złej strefie działają tylko `wersja`, `doktor`, `krok` i `aktualizuj`: `doktor` pokazuje wtedy ✗ „Strefa czasowa” z tym samym zdaniem, a `krok` pisze „Do poprawienia: Strefa czasowa. Szczegóły pokaże komenda doktor.”

**Co robisz:** popraw (za zgodą klienta) w `dane/config.json` nazwę strefy do formy `Europe/Warsaw` albo usuń wiersz `timezone`. Zły zapis `daily_max`, `hours`, `day_window` albo `brake_slot` kończy się komunikatem z nazwą ustawienia (kod wyjścia 1). Godziny `hours` i `brake_slot` muszą mieścić się w `day_window`, bo program nigdy nie planuje poza oknem publikacji.

**Brak bazy stref czasowych (zwykle Windows):** komunikat „Ten komputer nie ma bazy stref czasowych (pakiet tzdata nie działa), więc nie mogę liczyć terminów. Uruchom komendę doktor i zainstaluj pakiety jeszcze raz (krok „Programy”).” (kod wyjścia 2) znaczy, że zepsuta jest instalacja pakietów, a nie ustawienia: nie edytuj `dane/config.json`. `doktor` pokaże ✗ „Pakiety Pythona” i ✗ „Strefa czasowa” z tym samym zdaniem. Powtórz instalację pakietów z kroku 1 (`kroki/01-programy.md`) i uruchom `doktor`.

## Uszkodzony plik ustawień

**Objaw:** komenda pisze „Plik dane/config.json jest uszkodzony (linia N, kolumna N). Otwórz go w edytorze i popraw albo usuń: wtedy program wraca do ustawień domyślnych (konto Instagrama wybierzesz jeszcze raz komendą konto).” (kod wyjścia 1) albo „Plik dane/config.json ma zły układ: powinien zawierać obiekt, na przykład {"daily_max": 10}. Otwórz go w edytorze i popraw albo usuń: wtedy program wraca do ustawień domyślnych (konto Instagrama wybierzesz jeszcze raz komendą konto).” Działają wtedy tylko `wersja`, `doktor`, `krok` i `aktualizuj`. `doktor` pokazuje ✗ „Ustawienia (dane/config.json)” z tym samym zdaniem, a `krok` pisze „Do poprawienia: Ustawienia (dane/config.json). Szczegóły pokaże komenda doktor.”

**Przyczyna:** plik ręcznie edytowany ma błąd składni (brakujący przecinek między ustawieniami, typograficzny cudzysłów „…” zamiast prostego "…", niedomknięty nawias), nie jest obiektem JSON albo zapisano go w kodowaniu innym niż UTF-8.

**Co robisz:** za zgodą klienta popraw wskazane miejsce w `dane/config.json` narzędziem do edycji plików (numer linii i kolumny podaje komunikat) i uruchom `doktor`. Jeśli pliku nie da się uratować, za zgodą klienta usuń go: program wróci do ustawień domyślnych, więc konto Instagrama trzeba wybrać jeszcze raz (`konto`), a własne godziny i limity wpisać od nowa. Nie przepisuj pliku z pamięci: zapisane w nim `ig_account_id` i `ig_handle` pochodzą z komendy `konto`.

## Limity i zbyt duża liczba triali

Według dokumentacji Zernio na konto Instagram obowiązują limity (25 postów na godzinę i 100 na dobę). Przy domyślnych 10 triali dziennie ich nie dotykasz. Nie zwiększaj `daily_max` bez potrzeby: nie wiemy, jak Instagram zareaguje na bardzo dużo próbnych rolek, a od tego jest hamulec. Aktualne limity i cennik klient sprawdza w Zernio.

## Konto Instagram jest osobiste

**Objaw:** Zernio nie chce podłączyć konta albo trial się nie ustawia.

**Przyczyna:** triale i połączenie z Zernio wymagają konta profesjonalnego (twórca albo firma).

**Co robisz:** poproś klienta o przełączenie typu konta w ustawieniach Instagrama (bezpłatnie, można cofnąć) i ponowne podłączenie w Zernio.

## Czego program nie robi

Nie obiecuj klientowi rzeczy, których program nie umie:

- Obsługuje tylko Instagram. Nie ma TikToka, Facebooka ani YouTube.
- Jedna instalacja obsługuje jedno konto Instagram. Drugie konto wymaga osobnego folderu `trial-reels`.
- Działa na Macu (macOS 12 lub nowszy) i na Windowsie 10 lub 11 na procesorze x64. Windows na procesorze ARM nie jest obsługiwany (brakuje dla niego pakietów). Nie działa na Linuksie.
- Nie przepuszcza triali do obserwujących. To zawsze robi klient, w aplikacji Instagram.
- Nie loguje się nigdzie za klienta i nie zna jego haseł.

## Drobiazgi

- Komunikat w stylu „error: unrecognized arguments”, „the following arguments are required” albo „invalid choice” (po angielsku, z linią „usage”) i kod wyjścia 2 to błąd składni wywołania komendy, a nie problem klienta. Sprawdź nazwę i opcje w mapie komend w `SKILL.md`.
- Przy transkrypcji na Macu może pojawić się linia „Tip: experimental MPS backend…”, a przy pobieraniu modelu „Warning: You are sending unauthenticated requests to the HF Hub…” (ostrzeżenie, że pobieranie idzie bez konta Hugging Face). To szum biblioteki, nie błędy. Niczego nie trzeba robić.
- `kadr` na zbyt dużym `--t` pisze jedną linię po polsku: „Film ma tylko X s, więc nie ma w nim klatki z Y s. Podaj mniejszy czas w opcji --t.” Podaj mniejszy czas. Gdy czas mieści się w filmie, ale wypada tuż przed jego końcem (ostatnie 0,25 s), pisze: „Film ma X s, a tuż przed jego końcem nie ma już klatki do wyciągnięcia, więc nie ma jej w Y s. Podaj w opcji --t czas mniejszy niż Z s.” Udane `kadr` nadpisuje ten sam plik `kadr_KOD.jpg` rolki, a nieudane zostawia poprzednią klatkę.
- Na Windowsie z polskimi literami w nazwie użytkownika (np. `C:\Users\Łukasz Ząb`) model rozpoznawania mowy leży w `C:\Users\Public\trial-reels-model` (a gdy jest zmienna PUBLIC, w `%PUBLIC%\trial-reels-model`), a nie w `~/.cache/huggingface`, bo natywna biblioteka, która go czyta, potrafi nie otworzyć plików ze ścieżki z takimi znakami.
- Polskie litery w wyniku komend na Windowsie bywają wyświetlone jako dziwne znaki (częściej w PowerShellu). To zwykle problem wyświetlania, a nie danych: pliki w `dane/` są zapisane w UTF-8. Nie przepisuj ich i nie „naprawiaj”.
- Pula to do 12 rolek, a `pula --auto N` dopełnia ją do N aktywnych rolek. Kody rolek podawaj przed `--auto`, bo kod tuż za `--auto` zostałby potraktowany jak liczba.
- Usunięcie folderu `trial-reels` nie usuwa zaplanowanych postów w Zernio. Zrobi to klient w panelu Zernio.
