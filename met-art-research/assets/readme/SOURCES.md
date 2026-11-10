# README image sources

Images from The Metropolitan Museum of Art. The API marked each artwork as public domain when retrieved on November 10, 2026.

## Header images

### Hippopotamus ("William")

- Met object ID: 544227
- Date: ca. 1961–1878 B.C.
- Credit: Gift of Edward S. Harkness, 1917
- [Collection record](https://www.metmuseum.org/art/collection/search/544227)
- [Image source](https://images.metmuseum.org/CRDImages/eg/web-large/DP248993.jpg)

### Under the Wave off Kanagawa (Kanagawa oki nami ura), also known as The Great Wave, from the series Thirty-six Views of Mount Fuji (Fugaku sanjūrokkei)

- Met object ID: 45434
- Date: ca. 1830–32
- Artist: Katsushika Hokusai
- Credit: H. O. Havemeyer Collection, Bequest of Mrs. H. O. Havemeyer, 1929
- [Collection record](https://www.metmuseum.org/art/collection/search/45434)
- [Image source](https://images.metmuseum.org/CRDImages/as/web-large/DP130155.jpg)

### Cat

- Met object ID: 191965
- Date: ca. 1780
- Credit: Rogers Fund, 1912
- [Collection record](https://www.metmuseum.org/art/collection/search/191965)
- [Image source](https://images.metmuseum.org/CRDImages/es/web-large/DP-17550-003.jpg)

## Contact sheet: Cats

The example shows the first six public-domain works with available images from the first 24 results of a title search for `Cats`. The API reported 32 total matches at the time.

```sh
python3 skills/met-art-research/scripts/met.py search "Cats" --scope title --has-images --max-ids 24
python3 skills/met-art-research/scripts/met.py scan /returned/session/path --public-domain --has-images
python3 skills/met-art-research/scripts/met.py contact-sheet --session /returned/session/path --selection --limit 6 --columns 3 --rows 2
```

Result order and image availability may change. The numbered works in this example are:

### 1. Cats

- Met object ID: 337429
- Date: 1868–69
- Attribution or culture: Edouard Manet
- Credit: Rogers Fund, 1921
- [Collection record](https://www.metmuseum.org/art/collection/search/337429)
- [Image source](https://images.metmuseum.org/CRDImages/dp/web-large/DP815335.jpg)

### 2. [Four Cats]

- Met object ID: 271810
- Date: ca. 1895
- Attribution or culture: Thomas Eakins
- Credit: Gift of Joan and Martin E. Messinger, 1985
- [Collection record](https://www.metmuseum.org/art/collection/search/271810)
- [Image source](https://images.metmuseum.org/CRDImages/ph/web-large/DT8254.jpg)

### 3. Hollyhocks and Cats

- Met object ID: 51660
- Date: Not recorded
- Attribution or culture: Unidentified artist
- Credit: From the Collection of A. W. Bahr, Purchase, Fletcher Fund, 1947
- [Collection record](https://www.metmuseum.org/art/collection/search/51660)
- [Image source](https://images.metmuseum.org/CRDImages/as/web-large/DP154541.jpg)

### 4. Two Cats (from Sketchbook)

- Met object ID: 14884
- Date: ca. 1838 and after
- Attribution or culture: Francis William Edmonds
- Credit: Sheila and Richard J. Schwartz Fund, 1987
- [Collection record](https://www.metmuseum.org/art/collection/search/14884)
- [Image source](https://images.metmuseum.org/CRDImages/ad/web-large/246938.jpg)

### 5. Netsuke of Two Cats

- Met object ID: 59249
- Date: 19th century
- Attribution or culture: Japan
- Credit: Gift of Mrs. Russell Sage, 1910
- [Collection record](https://www.metmuseum.org/art/collection/search/59249)
- [Image source](https://images.metmuseum.org/CRDImages/as/web-large/LC-10_211_2035-001.jpg)

### 6. Dish Incised with Two Cats

- Met object ID: 308717
- Date: 3rd–2nd century BCE
- Attribution or culture: Paracas
- Credit: Gift of Mr. and Mrs. Nathan Cummings, 1964
- [Collection record](https://www.metmuseum.org/art/collection/search/308717)
- [Image source](https://images.metmuseum.org/CRDImages/ao/web-large/64.228.184.jpg)
