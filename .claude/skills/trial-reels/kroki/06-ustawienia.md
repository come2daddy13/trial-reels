**Krok 6: Ustawienia rolek**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Dla każdej rolki sprawdzamy, jak wygląda na niej napis z hookiem (biały dymek), i ustawiamy go tak, żeby niczego nie zasłaniał.

## Po co

Hook to napis w białym dymku na początku rolki. Jeśli w nagraniu są już wypalone napisy albo twoja twarz jest wysoko w kadrze, dymek mógłby je zasłonić. A jeśli na ekranie widać cudze dane (nazwiska, adresy e-mail, wiadomości od klientów), trzeba je rozmyć, zanim rolka pójdzie w świat w kilkunastu wersjach.

## Co robisz Ty

1. Patrz na obraz, który ci pokażę (otworzy się na twoim komputerze) i opiszę. Odpowiadaj na pytanie: „Czy dymek zasłania twoją twarz albo ważny napis?” Wystarczy „tak”, „nie” albo „niżej” i „wyżej”.
2. Powiedz, czy w którejś rolce na ekranie widać cudze dane i w którym momencie.
3. Powiedz, czy w którejś rolce padają słowa w rodzaju „napisz SŁOWO w komentarzu”, pod którymi masz działającą automatyczną odpowiedź (wiadomość po wpisaniu słowa). Jeśli nie wiesz, czy działa pod nowymi postami, odpowiedz „nie wiem”. Wtedy uznamy, że nie działa, i będzie można to zmienić później.
4. Zatwierdź ustawienia każdej rolki.

## Co robię ja

1. Dla każdej aktywnej rolki robię klatkę z próbnym hookiem, podstawiając kod rolki: `bash trial.sh kadr Cabc123XYZ_ --t 1` albo `.\trial.cmd kadr Cabc123XYZ_ --t 1`. Obraz trafia do `dane/wersje/kadr_KOD.jpg`. Udane `kadr` nadpisuje ten sam plik rolki (nieudane zostawia poprzednią klatkę), więc klatki tej samej rolki oglądam po kolei: robię klatkę, oglądam ją i dopiero potem robię następną. Robię kilka klatek w różnych momentach (np. `--t 0.5`, `--t 3` i `--t 8`), żeby zobaczyć napisy, które pojawiają się później. Hook zapisany już w `dane/hooki.json` pokazuję opcją `--hook-id h01` (tekst i emotkę program bierze z pliku), a krótki tekst na próbę opcją `--hook "tekst"`, w PowerShellu bez znaków & | ^ < > % i cudzysłowów. Klatka uwzględnia rozmycie z `blur`.
2. Obraz oglądam sam: odczytuję plik `dane/wersje/kadr_KOD.jpg` narzędziem do czytania plików (ono widzi obrazy) i opisuję klientowi, co jest na klatce: gdzie stoi dymek i czy zasłania twarz albo napis. Klientowi pokazuję ten sam plik na jego ekranie, podstawiając kod rolki: Mac `open dane/wersje/kadr_KOD.jpg`, Windows w PowerShellu `Start-Process dane\wersje\kadr_KOD.jpg`, w Git Bash `explorer "dane\wersje\kadr_KOD.jpg"`. Takie otwarcie pokazuje obraz tylko klientowi, a nie mnie.
3. Ustawiam w `dane/pula.json` pola opisane w „Dane klienta” w `SKILL.md`:
   - `hook_y` przesuwa dymek,
   - `mask` zasłania wypalony napis, który trwa długo (dymek zostaje przez całą rolkę),
   - `blur` rozmywa cudze dane,
   - `cuts` wycina z nagrania wypowiedziane zaproszenie ze słowem-kluczem, które u klienta nie działa (frazy dosłownie z `dane/transkrypcje/KOD.json`),
   - `strong`: czytam transkrypcję i proponuję 1–2 najmocniejsze zdania rolki, zwykle ze środka i zrozumiałe bez kontekstu. Klient wybiera. Bez `strong` rolka nie dostaje wersji „mocnych” (zimne otwarcie), co jest w porządku.
   - Rolka bez mowy (krok 5; `sprawdz-pule` pisze o niej „Informacja: … rolka bez mowy …”) nie ma czego wycinać ani cytować: `strong` i `cuts` zostają puste i taka rolka dostaje tylko wersje Subtelną i Średnią. `hook_y`, `mask` i `blur` ustawiam jak zwykle, bo patrzą na obraz, a nie na mowę.
4. Po zmianach robię kadr jeszcze raz i uruchamiam `bash trial.sh sprawdz-pule` albo `.\trial.cmd sprawdz-pule`. W tym kroku komenda będzie jeszcze zgłaszać braki hooków i dopisków (uzupełnimy je w kroku 7). Ważne, żeby nie zgłaszała problemów z frazami `strong` i `cuts`. Linie „Informacja:” o rolkach bez mowy to nie problem.
5. Po akceptacji klienta ustawiam w `dane/pula.json` `"ustawienia_ok": true` dla każdej zatwierdzonej rolki.

## Jak sprawdzamy

Obraz z `kadr` pokazuje dymek, który niczego nie zasłania. `sprawdz-pule` nie pisze, że jakiejś frazy „nie ma w transkrypcji” (linie „Informacja:” o rolkach bez mowy nie szkodzą). `krok` pokazuje krok `ustawienia` jako gotowy („Ustawienia zatwierdzone dla rolek: N.”).

## Gdy nie wychodzi

- Dymek zasłania napis. Przesuń `hook_y`. Jeśli napis jest przez całą rolkę albo jest szeroki, użyj `mask` z większym `min_w` i `min_h`. Gdy twarz jest wysoko w kadrze, dymek na górze zasłania głowę, więc zwiększ `hook_y` (np. do 0,4).
- „…nie ma w transkrypcji.” Fraza nie jest dosłownie taka jak w pliku z transkrypcją. Skopiuj ją stamtąd. Whisper czasem zapisuje słowa inaczej, niż się je wypowiada (liczby, skróty, słowa z łącznikiem, np. „e-mail”), więc patrz na to, co zapisał. Więcej w `PULAPKI.md`.
- `kadr` pisze „Film ma tylko X s, więc nie ma w nim klatki z Y s. Podaj mniejszy czas w opcji --t.” Rolka jest krótsza, niż zakładałem. Podaj `--t` mniejsze niż X (np. `--t 1`). To jedyna linia, bez angielskich komunikatów ffmpeg.
- `kadr` pisze „Film ma X s, a tuż przed jego końcem nie ma już klatki do wyciągnięcia, więc nie ma jej w Y s. Podaj w opcji --t czas mniejszy niż Z s.” Czas Y mieści się w filmie, ale tuż przed samym końcem klatki zwykle już nie ma. Podaj `--t` mniejsze niż Z.
- `kadr` pisze „Nie udało się wyciągnąć klatki z Y s: plik jest uszkodzony albo ffmpeg go nie odczytał.” Poproś klienta, żeby otworzył plik `dane/src/KOD.mp4` i sprawdził, czy się odtwarza. Jeśli się nie odtwarza, za zgodą klienta usuń ten plik i uruchom `pobierz` jeszcze raz.
- ffmpeg zgłasza inny błąd przy przygotowaniu kadru. Poproś klienta, żeby otworzył plik `dane/src/KOD.mp4` i sprawdził, czy się odtwarza.
- Klient nie ma pewności co do słowa-klucza. Uznajemy, że nie działa. To bezpieczniejsze: widz nie dostaje zaproszenia, na które nikt nie odpowie. W kroku 7 uzupełnimy zaproszenie w podpisie.
- Klient chce rozmyć coś, czego nie widać na jednej klatce. Zrób kilka klatek co 1–2 sekundy w miejscu, gdzie to się pojawia, i ustal przedział `t` w `blur` z zapasem po obu stronach.
