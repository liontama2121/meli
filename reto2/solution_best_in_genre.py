# -----------------------------------------------------------
# File: solution_best_in_genre.py
# Challenge: Mercado Libre Tech Challenge – Reto 2
# Task: REST API – Best TV Shows in Genre
# Author: Juan Camilo Molina León
# -----------------------------------------------------------


import requests


def bestInGenre(genre: str) -> str:
    """
    Encuentra la serie con la mayor calificación (imdb_rating)
    dentro del género especificado, utilizando la API pública
    https://jsonmock.hackerrank.com/api/tvseries.

    Si hay un empate en la calificación, devuelve la serie
    con el nombre alfabéticamente menor.

    Parámetros:
    -----------
    genre : str
        El género que se desea buscar (por ejemplo: "Action", "Drama", "Comedy")

    Retorna:
    --------
    str
        El nombre de la serie con mejor calificación dentro del género.
        Si no se encuentra ninguna serie del género, devuelve "No show found".
    """

    # URL base de la API (sin el número de página)
    base_url = "https://jsonmock.hackerrank.com/api/tvseries"

    # Empezamos por la primera página del API
    page = 1

    # Variables para guardar el mejor resultado hasta el momento
    best_show = None       # Nombre de la mejor serie encontrada
    best_rating = -1.0     # Calificación más alta encontrada

    # 🔁 Bucle para recorrer todas las páginas de resultados
    while True:
        # Construimos la URL incluyendo el número de página
        url = f"{base_url}?page={page}"

        # Enviamos una solicitud HTTP GET
        response = requests.get(url)

        # Si la respuesta no es exitosa (por ejemplo, error 404 o 500), detenemos el proceso
        if response.status_code != 200:
            print(f"⚠️ Error al obtener datos de la API en la página {page}. Código: {response.status_code}")
            break

        # Convertimos la respuesta JSON en un diccionario de Python
        data = response.json()

        # Extraemos la lista de series contenida en la clave "data"
        shows = data.get("data", [])

        # Recorremos cada serie de la página actual
        for show in shows:
            # Obtenemos el campo 'genre', lo separamos por comas y quitamos espacios
            genres = [g.strip() for g in show.get("genre", "").split(",")]

            # Si el género buscado está en la lista de géneros de la serie...
            if genre in genres:
                # Obtenemos la calificación y el nombre
                rating = float(show.get("imdb_rating", 0))
                name = show.get("name", "")

                # 🧩 Comparamos:
                # 1. Si la calificación es mayor que la mejor hasta ahora
                # 2. Si es igual, usamos orden alfabético del nombre
                if (rating > best_rating) or (rating == best_rating and (best_show is None or name < best_show)):
                    best_show = name
                    best_rating = rating

        # Si ya llegamos a la última página, terminamos el bucle
        if page >= data.get("total_pages", 1):
            break

        # Si no, pasamos a la siguiente página
        page += 1

    # Devolvemos el nombre de la mejor serie encontrada
    return best_show or "No show found"


# -----------------------------------------------------------
# 🔍 Bloque opcional de prueba local
# (No es necesario para la evaluación, pero útil para probar)
# -----------------------------------------------------------
if __name__ == "__main__":
    print("Buscando la mejor serie del género 'Action'...\n")
    result = bestInGenre("Action")
    print(f"✅ Mejor serie encontrada: {result}")
