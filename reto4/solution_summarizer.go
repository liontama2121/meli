// Reto 4: CLI que resume un archivo usando una API pública de GenAI.
// Requisitos del reto: aceptar --input y --type (short|medium|bullet),
// llamar un endpoint público (HuggingFace Inference API), reflejar el tipo en el prompt,
// imprimir a stdout y manejar errores de forma amigable.
// Doc API: https://huggingface.co/docs/api-inference

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

type hfRequest struct {
	Inputs     string                 `json:"inputs"`
	Parameters map[string]interface{} `json:"parameters,omitempty"`     
	Options    map[string]interface{} `json:"options,omitempty"`
}

func main() {
	var (
		inputPath string
		sumType   string
	)

	flag.StringVar(&inputPath, "input", "", "Ruta al archivo a resumir (también puede pasarse como argumento posicional).")
	flag.StringVar(&sumType, "type", "short", "Tipo de resumen: short | medium | bullet")
	flag.Parse()

	// Permitir argumento posicional para el input si no llegó por --input
	if inputPath == "" {
		args := flag.Args()
		if len(args) > 0 {
			inputPath = args[0]
		}
	}

	if inputPath == "" {
		fail("Error: debe especificar la ruta del archivo con --input o como argumento posicional, por ejemplo:\n  go run solution_summarizer.go --input article.txt --type bullet")
	}

	// Normalizar tipo
	sumType = strings.ToLower(strings.TrimSpace(sumType))
	if sumType != "short" && sumType != "medium" && sumType != "bullet" {
		fail("Error: --type debe ser uno de: short | medium | bullet")
	}

	content, err := os.ReadFile(inputPath)
	if err != nil {
		fail(fmt.Sprintf("No se pudo leer el archivo '%s': %v", inputPath, err))
	}

	// Modelo HuggingFace (puede cambiarse por env HF_MODEL)
	model := getenvDefault("HF_MODEL", "facebook/bart-large-cnn")
	endpoint := "https://api-inference.huggingface.co/models/" + model

	// Token opcional (free tier suele requerir token, pero depende del modelo)
	token := os.Getenv("HF_API_TOKEN")

	// Construir prompt según tipo
	prompt := buildPrompt(sumType, string(content), filepath.Base(inputPath))

	// Parámetros orientativos por tipo
	minLen, maxLen := lengthsFor(sumType)

	reqBody := hfRequest{
		Inputs: prompt,
		Parameters: map[string]interface{}{
			"min_length": minLen,
			"max_length": maxLen,
		},
		// options: wait_for_model true ayuda cuando el modelo está “warming up”
		Options: map[string]interface{}{
			"wait_for_model": true,
		},
	}

	b, _ := json.Marshal(reqBody)
	httpReq, _ := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(b))
	httpReq.Header.Set("Content-Type", "application/json")
	if token != "" {
		httpReq.Header.Set("Authorization", "Bearer "+token)
	}

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		fail(fmt.Sprintf("No se pudo contactar el endpoint de HuggingFace: %v", err))
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		// Mensaje de error amigable con pistas comunes
		fail(fmt.Sprintf("La API respondió %d.\nCausas comunes:\n- El modelo '%s' puede requerir token (defina HF_API_TOKEN).\n- El modelo puede estar iniciando (intente de nuevo).\n- Revise su conexión a Internet.\n\nRespuesta:\n%s",
			resp.StatusCode, model, truncate(string(body), 800)))
	}

	// La respuesta estándar de la pipeline 'summarization' es un array de objetos con "summary_text"
	// Ej: [{"summary_text": "...."}]
	summary, err := parseHFSummary(body)
	if err != nil {
		fail(fmt.Sprintf("No se pudo interpretar la respuesta de la API: %v\nRespuesta cruda:\n%s", err, truncate(string(body), 800)))
	}

	fmt.Println(summary)
}

// buildPrompt refleja el tipo en el enunciado enviado al modelo.
func buildPrompt(kind, text, file string) string {
	header := ""
	switch kind {
	case "short":
		header = "Summarize the following text in 1-2 sentences (concise):\n\n"
	case "medium":
		header = "Summarize the following text in one coherent paragraph:\n\n"
	case "bullet":
		header = "Summarize the following text as a list of clear bullet points:\n\n"
	}
	// Limpiar posibles espacios excesivos
	text = strings.TrimSpace(text)
	return header + text + "\n"
}

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

func parseHFSummary(body []byte) (string, error) {
	// Intento 1: arreglo de objetos con "summary_text"
	var arr1 []map[string]interface{}
	if err := json.Unmarshal(body, &arr1); err == nil && len(arr1) > 0 {
		if st, ok := arr1[0]["summary_text"].(string); ok && st != "" {
			return strings.TrimSpace(st), nil
		}
	}

	// Intento 2: algunos modelos devuelven objeto único
	var obj map[string]interface{}
	if err := json.Unmarshal(body, &obj); err == nil {
		if st, ok := obj["summary_text"].(string); ok && st != "" {
			return strings.TrimSpace(st), nil
		}
	}

	return "", errors.New("no se encontró 'summary_text' en la respuesta")
}

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

func fail(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}
