**Krok 9: Pomiar wyników**

*Przekaż klientowi „Co robimy”, „Po co” i „Co robisz Ty” własnymi słowami, krótko i po ludzku. Reszta to twoje instrukcje. Jeden krok naraz: poczekaj na „gotowe”, sprawdź wynik i dopiero idź dalej.*

## Co robimy

Ustalamy, jak będziemy odczytywać wyniki twoich triali (w Chrome albo ręcznie), i robimy próbny odczyt na jednej rolce.

## Po co

Instagram nie podaje programowi liczby nowych obserwujących z każdej rolki: nie ma jej ani w Zernio, ani w innym miejscu poza panelem statystyk w samym Instagramie. Raz w tygodniu program potrzebuje tych liczb, żeby wiedzieć, które rolki puszczać częściej, a które odłożyć na bok. Dlatego wybieramy teraz sposób, w jaki je dostanie.

## Co robisz Ty

1. Wybierz tryb:
   - **Chrome:** liczby odczytam sam z panelu statystyk w Chrome, w którym jesteś zalogowany(-a) na Instagramie. Rozszerzenie Claude in Chrome musi być zainstalowane i włączone, a Chrome otwarty w czasie odczytu (także w zadaniu tygodniowym). Jeśli zrobiliśmy to już w kroku 4, niczego nowego nie instalujesz.
   - **Ręcznie:** raz w tygodniu podasz mi liczby z aplikacji Instagram dla kilkunastu rolek (najwyżej 12 par liczb). To kilka minut.
2. Przy trybie Chrome zaloguj się na Instagramie w tej przeglądarce sam(a), jeśli jeszcze tego nie zrobiłeś(-aś).
3. Przy próbnym odczycie sprawdź ze mną, czy liczby zgadzają się z tym, co widzisz w aplikacji Instagram.

## Co robię ja

1. Tryb Chrome: biorę jedną rolkę z puli (`media_id` w `dane/pula.json`), otwieram jej panel w osobnej karcie (`https://www.instagram.com/insights/media/ID/?hl=en`, gdzie `ID` to numer mediów), wypisuję skrypt komendą `js-odczyt` i uruchamiam go na tej karcie. Czytam `views_raw` i `follows_raw` (szczegóły w „Odczyt liczb z panelu Instagrama” w `SKILL.md`). Zapisuję odczyt jako próbę na rolce wyjściowej, podstawiając jej kod i odczytane liczby: `bash trial.sh wynik-kandydata Cabc123XYZ_ --wyswietlenia "12,3 tys." --obserwujacy 9` albo `.\trial.cmd wynik-kandydata Cabc123XYZ_ --wyswietlenia "12,3 tys." --obserwujacy 9`.
2. Tryb ręczny: proszę klienta o dwie liczby jednej rolki z aplikacji („Wyświetlenia” i „Obserwowanie” w sekcji „Aktywność w profilu”) i zapisuję je tą samą komendą. Sprawdzam, że zapis typu „12,3 tys.” zostaje zrozumiany. Komenda drukuje wtedy wyświetlenia, obserwujących i wynik na 1000 wyświetleń.
3. Zapisuję tryb: `bash trial.sh krok --gotowe pomiar --wartosc chrome` albo `.\trial.cmd krok --gotowe pomiar --wartosc chrome`. Dla trybu ręcznego: `bash trial.sh krok --gotowe pomiar --wartosc reczny` albo `.\trial.cmd krok --gotowe pomiar --wartosc reczny`. Tryb można zmienić później tym samym zapisem z inną wartością.

## Jak sprawdzamy

Próbny odczyt zwrócił dwie liczby, a komenda `wynik-kandydata` je zapisała. `krok` pokazuje krok `pomiar` jako gotowy („Zapisane: chrome.” albo „Zapisane: reczny.”). Zadanie tygodniowe odczyta ten tryb z kroku `pomiar` (pole `szczegoly`).

## Gdy nie wychodzi

- Nie ma narzędzi przeglądarki. Rozszerzenie jest niezainstalowane, wyłączone albo niepołączone z aplikacją Claude. Poproś klienta o sprawdzenie. Jeśli rozszerzenie nie jest dostępne w jego planie albo nie chce go instalować, wybierz tryb ręczny.
- Skrypt zwraca `login: true`. Instagram prosi o logowanie w tym Chrome. Poproś klienta, żeby zalogował się sam, i spróbuj jeszcze raz. Nigdy nie loguj się za niego.
- Skrypt zwraca `error` bez `login`. Panel nie wczytał się albo ma inne etykiety. Odczekaj chwilę i spróbuj jeszcze raz. Jeśli to się powtarza, wybierz tryb ręczny i zachowaj pole `tekst` do opisu problemu.
- Instagram pokazuje weryfikację, ostrzeżenie albo prośbę o zgodę. Przerwij, niczego nie klikaj i powiedz o tym klientowi.
- Liczby wyglądają źle. Poproś klienta o porównanie z aplikacją. Wyświetlenia w panelu to wyświetlenia na Instagramie i Facebooku razem (więcej w `PULAPKI.md`).
- Klient nie może znaleźć liczb w aplikacji. Nazwy menu zależą od wersji. Poproś o opis albo zrzut ekranu i poszukajcie razem. Jeśli się nie uda, zapisz problem w opisie dla opiekuna.
