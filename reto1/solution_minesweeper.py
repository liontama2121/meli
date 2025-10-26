"""
Programa: Contador de minas vecinas (versión documentada)
Autor: Juan Camilo Molina
Descripción:
    Este programa simula la lógica básica del juego "Buscaminas".
    Dado un tablero representado como una matriz de 0s (sin mina) y 1s (con mina),
    se genera una nueva matriz que indica cuántas minas hay alrededor de cada celda.
    Las minas se representan con el número 9 en el resultado final.
"""

def contar_minas_vecinas(tablero):
    """
    Función que calcula la cantidad de minas vecinas alrededor de cada celda del tablero.

    Parámetros:
        tablero (list[list[int]]): Matriz que representa el tablero del juego.
                                   1 indica una mina, 0 indica una celda vacía.

    Retorna:
        list[list[int]]: Nueva matriz del mismo tamaño, donde:
                         - Cada celda contiene el número de minas vecinas.
                         - Las celdas con minas se marcan con el valor 9.
    """

    # ==========================
    # VARIABLES PRINCIPALES
    # ==========================
    filas = len(tablero)          # Total de filas del tablero
    columnas = len(tablero[0])    # Total de columnas del tablero

    # Crear una matriz resultado del mismo tamaño que el tablero, inicializada en ceros.
    resultado = [[0 for _ in range(columnas)] for _ in range(filas)]

    # ==========================
    # DIRECCIONES ADYACENTES
    # ==========================
    # Cada celda puede tener hasta 8 vecinos (diagonales, horizontales y verticales).
    # Cada tupla (af, ac) representa el desplazamiento en filas y columnas.
    direcciones = [
        (-1, -1), (-1, 0), (-1, 1),  # Celdas de arriba
        (0, -1),           (0, 1),   # Celdas laterales
        (1, -1),  (1, 0),  (1, 1)    # Celdas de abajo
    ]

    # ==========================
    # RECORRIDO DEL TABLERO
    # ==========================
    for f in range(filas):               # f = Fila actual
        for c in range(columnas):        # c = Columna actual

            if tablero[f][c] == 1:
                # Si la celda actual contiene una mina, se marca con 9
                resultado[f][c] = 9
            else:
                # Contador de minas vecinas
                contador = 0

                # Revisión de las 8 posibles direcciones
                for af, ac in direcciones:
                    nf, nc = f + af, c + ac  # nf = nueva fila, nc = nueva columna

                    # Validar que el vecino esté dentro de los límites del tablero
                    if 0 <= nf < filas and 0 <= nc < columnas:
                        # Si hay una mina en el vecino, aumentamos el contador
                        if tablero[nf][nc] == 1:
                            contador += 1

                # Guardar el número de minas vecinas en la celda actual
                resultado[f][c] = contador

    return resultado


def main():
    """
    Función principal del programa.
    Define un tablero de prueba y muestra el resultado
    de contar las minas vecinas.
    """

    # ==========================
    # TABLERO DE PRUEBA
    # ==========================
    tablero = [
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 1],
        [1, 1, 0, 0]
    ]

    # ajustar al usuario  a su acomodo 
    # Llamada a la función principal
    resultado = contar_minas_vecinas(tablero)

    # ==========================
    # IMPRESIÓN DE RESULTADOS
    # ==========================
    print("Resultado del tablero:")
    for fila in resultado:
        print(fila)


# ==========================
# EJECUCIÓN DEL PROGRAMA
# ==========================

if __name__ == "__main__":
    main()
