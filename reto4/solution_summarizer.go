<<<<<<< HEAD
// Reto 4: CLI que resume un archivo usando una API pública de GenAI.
// Requisitos del reto: aceptar --input y --type (short|medium|bullet),
// llamar un endpoint público (HuggingFace Inference API), reflejar el tipo en el prompt,
// imprimir a stdout y manejar errores de forma amigable.
// Doc API: https://huggingface.co/docs/api-inference
=======
// =============================================================
// Archivo: solution_summarizer.go
// Desafío: Mercado Libre DataSec Technical Challenge – Reto 4
// Descripción:
//   Aplicación de línea de comandos (CLI) escrita en Go que utiliza
//   un modelo de IA generativa (GenAI) público para resumir el contenido
//   de un archivo de texto.
//
// Requisitos oficiales del reto:
//   - La aplicación debe estar escrita en Go.
//   - Debe aceptar:
//       --input o argumento posicional → ruta al archivo a resumir.
//       --type (-t) → tipo de resumen: short | medium | bullet.
//   - Debe llamar una API pública de IA (por ejemplo Hugging Face).
//   - El prompt debe reflejar el tipo de resumen.
//   - Debe imprimir el resultado por consola (stdout).
//   - Debe manejar errores de manera amigable.
//   - Debe documentar la versión de Go usada.
//
// Documentación API: https://huggingface.co/docs/api-inference
// =============================================================
>>>>>>> e441529 (documentacion)

package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"net/http"
	"path/filepath"
	"strings"
	"time"
)

// -------------------------------------------------------------
// Estructura del cuerpo de la solicitud a la API de Hugging Face
// -------------------------------------------------------------
type hfRequest struct {
	Inputs     string                 `json:"inputs"`                  // Texto o prompt que se enviará al modelo
	Parameters map[string]interface{} `json:"parameters,omitempty"`    // Parámetros opcionales (min_length, max_length, etc.)
	Options    map[string]interface{} `json:"options,omitempty"`       // Opciones adicionales (espera de modelo, etc.)
}

// -------------------------------------------------------------
// Función principal: procesa argumentos, lee archivo, construye
// prompt y solicita el resumen al modelo Hugging Face.
// -------------------------------------------------------------
func main() {
	var (
		inputPath string
		sumType   string
	)

	// Definición de parámetros de línea de comandos
	flag.StringVar(&inputPath, "input", "", "Ruta del archivo a resumir (también puede pasarse como argumento posicional).")
	flag.StringVar(&sumType, "type", "short", "Tipo de resumen: short | medium | bullet")
	flag.Parse()

	// Permitir pasar el archivo como argumento posicional
	if inputPath == "" {
		args := flag.Args()
		if len(args) > 0 {
			inputPath = args[0]
		}
	}

	// Validar que se haya proporcionado un archivo
	if inputPath == "" {
		fail("Error: debe especificar la ruta del archivo con --input o como argumento posicional.\nEjemplo:\n  go run solution_summarizer.go --input article.txt --type bullet")
	}

	// Normalizar y validar el tipo de resumen
	sumType = strings.ToLower(strings.TrimSpace(sumType))
	if sumType != "short" && sumType != "medium" && sumType != "bullet" {
		fail("Error: --type debe ser uno de: short | medium | bullet")
	}

	// Leer el contenido del archivo
	content, err := os.ReadFile(inputPath)
	if err != nil {
		fail(fmt.Sprintf("No se pudo leer el archivo '%s': %v", inputPath, err))
	}

	// Configuración del modelo (por defecto usa BART, pero se puede cambiar con la variable HF_MODEL)
	model := getenvDefault("HF_MODEL", "facebook/bart-large-cnn")
	endpoint := "https://api-inference.huggingface.co/models/" + model

	// Token opcional de Hugging Face (solo necesario en algunos modelos)
	token := os.Getenv("HF_API_TOKEN")

	// Construir el prompt dinámico según el tipo de resumen solicitado
	prompt := buildPrompt(sumType, string(content), filepath.Base(inputPath))

	// Ajustar parámetros del resumen según el tipo
	minLen, maxLen := lengthsFor(sumType)

	// Crear el cuerpo de la solicitud JSON
	reqBody := hfRequest{
		Inputs: prompt,
		Parameters: map[string]interface{}{
			"min_length": minLen,
			"max_length": maxLen,
		},
		Options: map[string]interface{}{
			"wait_for_model": true, // Asegura que el modelo cargue si está "warming up"
		},
	}

	// Preparar la solicitud HTTP POST
	b, _ := json.Marshal(reqBody)
	httpReq, _ := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(b))
	httpReq.Header.Set("Content-Type", "application/json")
	if token != "" {
		httpReq.Header.Set("Authorization", "Bearer "+token)
	}

	// Cliente HTTP con tiempo de espera razonable
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		fail(fmt.Sprintf("No se pudo contactar el endpoint de Hugging Face: %v", err))
	}
	defer resp.Body.Close()

	// Leer la respuesta
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		fail(fmt.Sprintf("La API respondió %d.\nCausas posibles:\n- El modelo '%s' requiere token (defina HF_API_TOKEN).\n- El modelo está iniciando, intente de nuevo.\n- Revise su conexión a Internet.\n\nRespuesta:\n%s",
			resp.StatusCode, model, truncate(string(body), 800)))
	}

	// Procesar el JSON devuelto por el modelo
	summary, err := parseHFSummary(body)
	if err != nil {
		fail(fmt.Sprintf("No se pudo interpretar la respuesta de la API: %v\nRespuesta cruda:\n%s", err, truncate(string(body), 800)))
	}

	// Imprimir resumen final al usuario
	fmt.Println(summary)
}

// -------------------------------------------------------------
// buildPrompt: genera el texto que se enviará al modelo, adaptando
// el enunciado según el tipo de resumen solicitado.
// -------------------------------------------------------------
func buildPrompt(kind, text, file string) string {
	header := ""
	switch kind {
	case "short":
		header = "Resume el siguiente texto en 1-2 oraciones concisas:\n\n"
	case "medium":
		header = "Resume el siguiente texto en un solo párrafo coherente:\n\n"
	case "bullet":
		header = "Resume el siguiente texto en una lista de puntos claros:\n\n"
	}
	text = strings.TrimSpace(text)
	return header + text + "\n"
}

// -------------------------------------------------------------
// lengthsFor: define los valores mínimos y máximos de longitud
// del resumen según el tipo seleccionado.
// -------------------------------------------------------------
func lengthsFor(kind string) (int, int) {
	switch kind {
	case "short":
		return 20, 60
	case "medium":
		return 60, 180
	case "bullet":
		return 60, 200
	default:
		return 40, 120
	}
}

// -------------------------------------------------------------
// parseHFSummary: interpreta el JSON devuelto por la API para
// extraer el texto del resumen generado.
// -------------------------------------------------------------
func parseHFSummary(body []byte) (string, error) {
	var arr1 []map[string]interface{}
	if err := json.Unmarshal(body, &arr1); err == nil && len(arr1) > 0 {
		if st, ok := arr1[0]["summary_text"].(string); ok && st != "" {
			return strings.TrimSpace(st), nil
		}
	}

	var obj map[string]interface{}
	if err := json.Unmarshal(body, &obj); err == nil {
		if st, ok := obj["summary_text"].(string); ok && st != "" {
			return strings.TrimSpace(st), nil
		}
	}
	return "", errors.New("no se encontró 'summary_text' en la respuesta")
}

// -------------------------------------------------------------
// Funciones auxiliares: obtener variables de entorno y truncar texto
// -------------------------------------------------------------
func getenvDefault(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func truncate(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "...(truncated)"
}

// -------------------------------------------------------------
// fail: imprime errores y finaliza la ejecución del programa.
// -------------------------------------------------------------
func fail(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}
