-- 1️⃣ Unimos clientes con campañas
-- 2️⃣ Unimos campañas con eventos
-- 3️⃣ Filtramos solo los eventos con estado 'failure'
-- 4️⃣ Agrupamos por cliente
-- 5️⃣ Contamos los fallos
-- 6️⃣ Mostramos solo los clientes con más de 3 fallos

SELECT 
    CONCAT(c.first_name, ' ', c.last_name) AS customer,
    COUNT(e.status) AS failures
FROM customers c
INNER JOIN campaigns ca ON c.id = ca.customer_id
INNER JOIN events e ON ca.id = e.campaign_id
WHERE e.status = 'failure'
GROUP BY c.id, c.first_name, c.last_name
HAVING COUNT(e.status) > 3
ORDER BY failures DESC;
