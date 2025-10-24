-- ==============================================================
-- Archivo: solution_failures_report.sql
-- Desafío: Mercado Libre DataSec Technical Challenge – Reto 3
-- Descripción:
--   Consulta SQL que genera un reporte con los clientes que tienen
--   más de 3 eventos fallidos ('failure') en sus campañas publicitarias.
--
-- Tablas involucradas:
--   - customers  (id, first_name, last_name)
--   - campaigns  (id, customer_id, name)
--   - events     (dt, campaign_id, status)
--
-- Salida esperada:
--   customer          | failures
--   ------------------|----------
--   Whitney Ferrero   | 6
--
-- Notas:
--   • Cada cliente puede tener múltiples campañas.
--   • Cada campaña puede tener múltiples eventos (éxito o fallo).
--   • Solo se deben contar los eventos con estado 'failure'.
--   • Se deben mostrar únicamente los clientes con más de 3 fallos.
--
-- Compatible con:
--   PostgreSQL / MySQL / SQLite 3
-- ==============================================================

SELECT 
    -- Combina el nombre y apellido del cliente en una sola columna
    CONCAT(c.first_name, ' ', c.last_name) AS customer,
    
    -- Cuenta la cantidad de eventos con fallo por cliente
    COUNT(e.status) AS failures

FROM customers c
    -- Une la tabla de clientes con la de campañas
    INNER JOIN campaigns ca 
        ON c.id = ca.customer_id

    -- Une las campañas con la tabla de eventos
    INNER JOIN events e 
        ON ca.id = e.campaign_id

-- Filtra únicamente los eventos que tienen estado 'failure'
WHERE e.status = 'failure'

-- Agrupa los resultados por cliente para contar sus fallos
GROUP BY c.id, c.first_name, c.last_name

-- Muestra solo los clientes que tienen más de 3 fallos
HAVING COUNT(e.status) > 3

-- Ordena los resultados de mayor a menor cantidad de fallos
ORDER BY failures DESC;
