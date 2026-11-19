**Krok 7: Hooki i podpisy**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Piszemy hooki i podpisy dla każdej rolki i zatwierdzamy je razem.

## Po co

Hook, czyli napis na początku rolki, decyduje, czy obcy człowiek zatrzyma się na twojej rolce. Podpis jest tym samym tekstem co oryginalny, z lekkimi zmianami, żeby każda wersja trochę się różniła. Każde zdanie wyjdzie pod twoim nazwiskiem, więc to ty decydujesz, co zostaje.

## Co robisz Ty

1. Czytaj propozycje: po 5 hooków na rolkę (na start wystarczy), kilka wariantów zaproszenia do działania (CTA) i dopiski, które program dokleja na końcu podpisu. Rolki bez mowy dostaną hooki ułożone z ich podpisu i z obrazu.
2. Skreśl to, co ci nie pasuje, i popraw według własnego stylu. Hook ma brzmieć jak ty, a nie jak reklama.
3. Odpowiedz, czy słowo-klucz z zaproszenia ma zostać. Zostaje tylko wtedy, gdy twoja automatyczna odpowiedź naprawdę działa pod nowymi postami.
4. Zatwierdź rolkę po rolce albo całość naraz. Możemy to rozłożyć na kilka posiedzeń: po kilka rolek naraz.
5. Gdy wszystkie rolki są zatwierdzone, to dobry moment na przerwę. Postęp jest zapisany w plikach, a w nowej rozmowie zaczniemy od kroku 8.

## Co robię ja

1. Dla każdej aktywnej rolki czytam transkrypcję i oryginalny podpis (`caption` w `dane/pula.json`). Piszę bank 5 hooków w `dane/hooki.json` (na start wystarczy, program wymaga co najmniej 3) według zasad z „Hooki, podpisy i dopiski” w `SKILL.md`: szeroki hook (objaw, pragnienie, liczba albo kontrowersja), bez etykiety niszy, do 50 znaków, jedna emotka z zestawu, styl z rolek klienta. Przy rolce bez mowy (transkrypcja ma 0 słów) nie czytam transkrypcji, bo jest pusta: hooki i podpis układam z jej podpisu i z obrazu (klatki z kroku 6, napisy na ekranie) i niczego nie cytuję z transkrypcji. Gdy podpis jest pusty albo nic nie mówi, pytam klienta jednym zdaniem, o czym jest rolka.
2. Pisanie hooków można rozłożyć na kilka posiedzeń, gdy limit klienta jest ciasny: po kilka rolek naraz, każdą zatwierdzam osobno (`hooki_ok`), a `krok` pokazuje, którym rolkom jeszcze brakuje zatwierdzenia. Gdy bank się wyczerpie (przy 5 hookach zwykle w pierwszym tygodniu), program robi powtórki najlepszych hooków i pisze „Bank hooków prawie pusty”. Więcej hooków dopisujemy później, na osobnym posiedzeniu.
3. W `dane/pula.json` ustawiam `cta` (dokładny fragment podpisu z zaproszeniem), `cta_variants` (2–3 inne sformułowania z tym samym @nick i słowem-kluczem w „…”) i `extras` (co najmniej 4 krótkie dopiski wynikające z tego, co klient mówi w rolce, bez długiego myślnika). Jeśli słowo-klucz nie działa, zamieniam w `caption` to zdanie na zwykłe zaproszenie do obserwowania, wpisuję w `cta` dokładnie to samo zdanie i, jeśli rolka ma mowę, pilnuję, żeby `cuts` z kroku 6 wycinało wypowiedziane zaproszenie. Gdy podpis rolki w ogóle nie ma zaproszenia, `cta` i `cta_variants` zostają nieustawione (`cta` jest opcjonalne), a dopisuję tylko `extras`.
4. Pokazuję klientowi całość czytelnie: hooki w liście oraz przykładowy podpis złożony z jednego wariantu i jednego dopisku. Poprawiam według jego uwag.
5. Uruchamiam `bash trial.sh sprawdz-pule` albo `.\trial.cmd sprawdz-pule` i poprawiam, aż pojawi się „Pula gotowa: N rolek”. Linie „Informacja:” po tym zdaniu dotyczą rolek bez mowy i nie są problemem.
6. Po akceptacji klienta ustawiam w `dane/pula.json` `"hooki_ok": true` dla każdej zatwierdzonej rolki.
7. Gdy wszystkie rolki są zatwierdzone, proponuję klientowi przerwę (patrz „Oszczędzaj limit klienta” w `CLAUDE.md`). W nowej rozmowie zaczniemy od kroku 8.

## Jak sprawdzamy

`sprawdz-pule` kończy się komunikatem „Pula gotowa: N rolek”. `krok` pokazuje krok `hooki` jako gotowy („Hooki i podpisy zatwierdzone dla rolek: N. Pula przechodzi sprawdzenie.”).

## Gdy nie wychodzi

Komunikaty `sprawdz-pule` zaczynają się od „Rolka NAZWA (KOD):”. Najczęstsze i co z nimi zrobić:

- „za mało hooków w hooki.json”. Potrzeba co najmniej 3, a na start piszemy 5. Dopisz.
- „tekst ma N znaków, a limit to 50”. Skróć hook.
- „w tekście jest emotka”. Przenieś ją do pola `emoji`.
- „emotki … nie ma w zestawie”. Wybierz emotkę z listy w `SKILL.md`.
- „emotka ma niewidoczny znak U+FE0F”. Wpisz samą emotkę z listy, bez tego znaku.
- „wariant CTA … gubi: …”. Wariant musi zawierać ten sam @nick i to samo słowo-klucz w „…”. Nie zamieniaj typograficznych cudzysłowów „…” na proste.
- „tekstu z pola cta nie ma w podpisie”. Skopiuj `cta` z `caption` znak w znak. Gdy podpis nie ma żadnego zaproszenia, usuń pole `cta` (jest opcjonalne).
- „rolka nie ma mowy (transkrypcja ma 0 słów), więc pola strong i cuts nie mają sensu. Usuń je z dane/pula.json.” Rolka bez mowy nie potrzebuje `strong` ani `cuts`. Usuń oba pola z tej rolki.
- „za mało dopisków w polu extras”. Potrzeba co najmniej 4.
- „dopisek albo wariant CTA ma myślnik”. Zamień długi myślnik na kropkę, przecinek albo dwukropek.
- „podpis wersji N ma M znaków, a Instagram przyjmuje najwyżej 2200”. Skróć `caption` albo dopiski.

Inne sytuacje:

- Klient chce hooków „ostrzejszych”. Trzymaj się zasad: bez obietnic, bez etykiety niszy, bez niczego, czego rolka nie mówi.
- Klient nie ma słowa-klucza w ogóle. Zamień w `caption` zdanie z zaproszeniem na zwykłe zaproszenie do obserwowania, np. „Zaobserwuj @przyklad.konto, jeśli chcesz więcej takich treści”, i wpisz w `cta` dokładnie to samo zdanie. Jeśli podpis rolki w ogóle nie ma zaproszenia, nie dopisuj go na siłę: zostaw rolkę bez `cta`.
- Klient pisze lepsze hooki od ciebie. Świetnie: wpisz je do `dane/hooki.json` tak, jak je podał, i tylko sprawdź limit i emotkę.
