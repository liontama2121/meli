// server.go
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
)

// =================== Config HF ===================
type hfRequest struct {
	Inputs     string                 `json:"inputs"`
	Parameters map[string]interface{} `json:"parameters,omitempty"`
	Options    map[string]interface{} `json:"options,omitempty"`
}

const (
	defaultModel         = "facebook/bart-large-cnn"
	hfAPIBase            = "https://api-inference.huggingface.co/models/"
	clientTimeout        = 60 * time.Second
	maxCharsPerChunk     = 4000
	maxJoinForSecondPass = 6000
)

// =================== API Types ===================
type summarizeRequest struct {
	Text          string  `json:"text"`
	Type          string  `json:"type"`           // short | medium | bullet
	Privacy       string  `json:"privacy"`        // mask | redact
	StripNames    bool    `json:"strip_names"`    // heurística nombres propios
	MinLength     int     `json:"min_length"`     // opcional override
	MaxLength     int     `json:"max_length"`     // opcional override
	NumBeams      int     `json:"num_beams"`      // >=1
	LengthPenalty float64 `json:"length_penalty"` // >0
	Bullets       int     `json:"bullets"`        // si type=bullet
}

type summarizeResponse struct {
	Summary string `json:"summary"`
}

// =================== HTTP Server ===================
func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/summarize", withCORS(summarizeHandler))
	mux.HandleFunc("/healthz", withCORS(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"ok": "true"})
	}))

	port := getenvDefault("PORT", "8080")
	fmt.Fprintf(os.Stderr, "Listening on :%s\n", port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		panic(err)
	}
}

func withCORS(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		h(w, r)
	}
}

func summarizeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "use POST"})
		return
	}

	var req summarizeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "JSON inválido"})
		return
	}
	req.Type = strings.ToLower(strings.TrimSpace(req.Type))
	if req.Type == "" {
		req.Type = "medium"
	}
	if req.Privacy == "" {
		req.Privacy = "redact"
	}
	if req.NumBeams <= 0 {
		req.NumBeams = 6
	}
	if req.LengthPenalty <= 0 {
		req.LengthPenalty = 1.4
	}
	if req.Type == "bullet" && req.Bullets <= 0 {
		req.Bullets = 6
	}

	model := getenvDefault("HF_MODEL", defaultModel)
	token := os.Getenv("HF_API_TOKEN")
	endpoint := hfAPIBase + model

	// Debug mínimo
	tokPrev := token
	if len(tokPrev) > 6 {
		tokPrev = tokPrev[:6]
	}
	fmt.Fprintf(os.Stderr, "DEBUG model=%s token_len=%d\n", model, len(token))
	if token != "" {
		fmt.Fprintf(os.Stderr, "DEBUG header Authorization: Bearer %s...\n", tokPrev)
	} else {
		fmt.Fprintln(os.Stderr, "DEBUG sin token (algunos modelos lo requieren)")
	}

	// 1) Scrubbing PII de entrada
	clean := scrubPII(req.Text, req.Privacy, req.StripNames)

	// 2) Header guía según tipo
	header := buildHeader(req.Type, req.Bullets)
	if header != "" {
		clean = header + "\n\n" + clean
	}

	// 3) Chunking + llamada a HF
	minLen, maxLen := lengthsFor(req.Type)
	if req.MinLength > 0 {
		minLen = req.MinLength
	}
	if req.MaxLength > 0 {
		maxLen = req.MaxLength
	}
	if maxLen < minLen {
		maxLen = minLen + 40
	}

	client := &http.Client{Timeout: clientTimeout}
	chunks := chunkText(strings.TrimSpace(clean), maxCharsPerChunk)

	var parts []string
	for i, ch := range chunks {
		s, err := callHF(client, endpoint, token, ch, minLen, maxLen, req.NumBeams, req.LengthPenalty)
		if err != nil {
			if isRetryable(err) && len(ch) > 1000 {
				fmt.Fprintf(os.Stderr, "WARN chunk %d rechazado; reintento con recorte\n", i+1)
				chTrim := safeTrim(ch, len(ch)/2)
				s, err = callHF(client, endpoint, token, chTrim, max(minLen/2, 10), max(maxLen/2, 60), max(req.NumBeams/2, 1), req.LengthPenalty)
			}
		}
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "HF: " + err.Error()})
			return
		}
		parts = append(parts, s)
	}

	final := strings.Join(parts, "\n\n")
	if len(chunks) > 1 {
		if len(final) > maxJoinForSecondPass {
			final = safeTrim(final, maxJoinForSecondPass)
		}
		s2, err := callHF(client, endpoint, token, final, minLen, maxLen, req.NumBeams, req.LengthPenalty)
		if err != nil && isRetryable(err) {
			final = strings.Join(parts, "\n")
			final = safeTrim(final, maxJoinForSecondPass/2)
			s3, err2 := callHF(client, endpoint, token, final, max(minLen/2, 10), max(maxLen/2, 60), max(req.NumBeams/2, 1), req.LengthPenalty)
			if err2 == nil {
				writeJSON(w, http.StatusOK, summarizeResponse{Summary: strings.TrimSpace(scrubPIIOut(s3))})
				return
			}
		}
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "HF (segundo pase): " + err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, summarizeResponse{Summary: strings.TrimSpace(scrubPIIOut(s2))})
		return
	}

	writeJSON(w, http.StatusOK, summarizeResponse{Summary: strings.TrimSpace(scrubPIIOut(final))})
}

// =================== HF Call ===================
func callHF(client *http.Client, endpoint, token, input string, minLen, maxLen, beams int, lenPenalty float64) (string, error) {
	if beams < 1 {
		beams = 1
	}
	if lenPenalty <= 0 {
		lenPenalty = 1.0
	}
	reqBody := hfRequest{
		Inputs: input,
		Parameters: map[string]interface{}{
			"do_sample":            false,
			"min_length":           minLen,
			"max_length":           maxLen,
			"num_beams":            beams,
			"length_penalty":       lenPenalty,
			"no_repeat_ngram_size": 3,
		},
		Options: map[string]interface{}{
			"wait_for_model": true,
		},
	}
	b, _ := json.Marshal(reqBody)

	req, _ := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("no se pudo contactar la API: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("API %d: %s", resp.StatusCode, truncate(string(body), 500))
	}

	// [{"summary_text":"..."}] o [{"generated_text":"..."}]
	if s, err := parseHFSummary(body); err == nil && s != "" {
		return s, nil
	}
	if s := parseHFGeneratedText(body); s != "" {
		return s, nil
	}
	return "", errors.New("no se pudo interpretar la respuesta de la API")
}

func parseHFSummary(body []byte) (string, error) {
	var arr []map[string]interface{}
	if err := json.Unmarshal(body, &arr); err == nil && len(arr) > 0 {
		if st, ok := arr[0]["summary_text"].(string); ok && st != "" {
			return strings.TrimSpace(st), nil
		}
	}
	var obj map[string]interface{}
	if err := json.Unmarshal(body, &obj); err == nil {
		if st, ok := obj["summary_text"].(string); ok && st != "" {
			return strings.TrimSpace(st), nil
		}
	}
	return "", errors.New("sin 'summary_text'")
}

func parseHFGeneratedText(body []byte) string {
	var arr []map[string]interface{}
	if err := json.Unmarshal(body, &arr); err == nil && len(arr) > 0 {
		if gt, ok := arr[0]["generated_text"].(string); ok && gt != "" {
			return strings.TrimSpace(gt)
		}
	}
	var obj map[string]interface{}
	if err := json.Unmarshal(body, &obj); err == nil {
		if gt, ok := obj["generated_text"].(string); ok && gt != "" {
			return strings.TrimSpace(gt)
		}
	}
	return ""
}

// =================== PII Scrubbing (entrada/salida) ===================

// Entrada: versión “blindada” (IPv4/IPv6 + emails + phones + cuentas + tarjetas + IDs + nombres opcional)
func scrubPII(s, privacy string, stripNames bool) string {
	out := strings.ReplaceAll(s, "\u00A0", " ")

	reCard := regexp.MustCompile(`\b(?:\d[ -]*?){13,19}\b`)
	reAccount := regexp.MustCompile(`\b\d{3,4}[- ]\d{3,4}[- ]\d{3,}\b`)

	reIPv4Loose := regexp.MustCompile(`(?:\d{1,3}\.){3}\d{1,3}`)
	reIPv4WithLabel := regexp.MustCompile(`(?i)\bIP[ \t]+(?:\d{1,3}\.){3}\d{1,3}`)
	reIPv6 := regexp.MustCompile(`(?i)(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}`)
	reEmail := regexp.MustCompile(`(?i)([a-z0-9._%+\-]+)@([a-z0-9.\-]+\.[a-z]{2,})`)

	rePhone := regexp.MustCompile(`\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?)?\d{3,4}[ -]?\d{4}\b`)
	reID := regexp.MustCompile(`\b(?:ID|CC|NIT|DNI|SSN)[:\s\-]*[A-Z0-9\-]{4,}\b`)

	switch strings.ToLower(privacy) {
	case "mask":
		out = reCard.ReplaceAllString(out, "[CARD]")
		out = reAccount.ReplaceAllString(out, "[ACCOUNT]")

		out = reIPv4WithLabel.ReplaceAllString(out, "[IP]")
		out = reIPv4Loose.ReplaceAllString(out, "[IP]")
		out = reIPv6.ReplaceAllString(out, "[IP]")

		out = reEmail.ReplaceAllStringFunc(out, func(m string) string {
			parts := reEmail.FindStringSubmatch(m)
			if len(parts) == 3 {
				local, domain := parts[1], parts[2]
				if len(local) > 1 {
					local = local[:1] + strings.Repeat("*", len(local)-1)
				}
				dm := strings.Repeat("*", 3)
				if dot := strings.LastIndex(domain, "."); dot > 0 {
					dm = strings.Repeat("*", dot) + domain[dot:]
				}
				return local + "@" + dm
			}
			return "[EMAIL]"
		})
		out = rePhone.ReplaceAllString(out, "[PHONE]")
		out = reID.ReplaceAllString(out, "[ID]")
	default: // redact
		out = reCard.ReplaceAllString(out, "[CARD]")
		out = reAccount.ReplaceAllString(out, "[ACCOUNT]")

		out = reIPv4WithLabel.ReplaceAllString(out, "[IP]")
		out = reIPv4Loose.ReplaceAllString(out, "[IP]")
		out = reIPv6.ReplaceAllString(out, "[IP]")

		out = reEmail.ReplaceAllString(out, "[EMAIL]")
		out = rePhone.ReplaceAllString(out, "[PHONE]")
		out = reID.ReplaceAllString(out, "[ID]")
	}

	if stripNames {
		reNames := regexp.MustCompile(`\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)\b`)
		out = reNames.ReplaceAllString(out, "[NAME]")
	}

	out = regexp.MustCompile(`\s{2,}`).ReplaceAllString(out, " ")
	return strings.TrimSpace(out)
}

// Salida: por si el modelo “reconstruye” PII
func scrubPIIOut(s string) string {
	out := strings.ReplaceAll(s, "\u00A0", " ")

	replacements := []struct {
		re   *regexp.Regexp
		with string
	}{
		{regexp.MustCompile(`(?i)\bIP[ \t]+(?:\d{1,3}\.){3}\d{1,3}`), "[IP]"},
		{regexp.MustCompile(`(?:\d{1,3}\.){3}\d{1,3}`), "[IP]"},
		{regexp.MustCompile(`(?i)(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}`), "[IP]"},
		{regexp.MustCompile(`(?i)([a-z0-9._%+\-]+)@([a-z0-9.\-]+\.[a-z]{2,})`), "[EMAIL]"},
		{regexp.MustCompile(`\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?)?\d{3,4}[ -]?\d{4}\b`), "[PHONE]"},
		{regexp.MustCompile(`\b(?:\d[ -]*?){13,19}\b`), "[CARD]"},
		{regexp.MustCompile(`\b\d{3,4}[- ]\d{3,4}[- ]\d{3,}\b`), "[ACCOUNT]"},
		{regexp.MustCompile(`\b(?:ID|CC|NIT|DNI|SSN)[:\s\-]*[A-Z0-9\-]{4,}\b`), "[ID]"},
	}
	for _, r := range replacements {
		out = r.re.ReplaceAllString(out, r.with)
	}
	out = strings.ReplaceAll(out, "[PHONE)", "[PHONE]")
	out = regexp.MustCompile(`(?i)\bIP[ \t]+\[IP\]`).ReplaceAllString(out, "[IP]")
	return strings.TrimSpace(out)
}

// =================== Helpers ===================
func buildHeader(kind string, bullets int) string {
	switch kind {
	case "bullet":
		if bullets <= 0 {
			bullets = 6
		}
		return fmt.Sprintf("Resume el siguiente texto en %d viñetas claras y detalladas, evitando PII/PCI:", bullets)
	case "medium":
		return "Resume el siguiente texto en 1–3 párrafos claros y detallados, evitando PII/PCI:"
	default:
		return ""
	}
}

func lengthsFor(kind string) (int, int) {
	switch kind {
	case "short":
		return 40, 120
	case "medium":
		return 120, 260
	case "bullet":
		return 120, 300
	default:
		return 60, 160
	}
}

func chunkText(text string, limit int) []string {
	if len(text) <= limit {
		return []string{text}
	}
	paras := strings.Split(text, "\n\n")
	var chunks []string
	var buf strings.Builder
	for _, p := range paras {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		if buf.Len()+len(p)+2 <= limit {
			if buf.Len() > 0 {
				buf.WriteString("\n\n")
			}
			buf.WriteString(p)
		} else {
			if buf.Len() > 0 {
				chunks = append(chunks, buf.String())
				buf.Reset()
			}
			if len(p) <= limit {
				buf.WriteString(p)
			} else {
				sentences := splitBySentence(p)
				var sb2 strings.Builder
				for _, s := range sentences {
					if sb2.Len()+len(s)+1 <= limit {
						if sb2.Len() > 0 {
							sb2.WriteString(" ")
						}
						sb2.WriteString(s)
					} else {
						if sb2.Len() > 0 {
							chunks = append(chunks, sb2.String())
							sb2.Reset()
						}
						if len(s) <= limit {
							sb2.WriteString(s)
						} else {
							chunks = append(chunks, safeTrim(s, limit))
						}
					}
				}
				if sb2.Len() > 0 {
					chunks = append(chunks, sb2.String())
				}
			}
		}
	}
	if buf.Len() > 0 {
		chunks = append(chunks, buf.String())
	}
	return chunks
}

func splitBySentence(p string) []string {
	parts := strings.Split(p, ".")
	var out []string
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if !strings.HasSuffix(part, ".") {
			part += "."
		}
		out = append(out, part)
	}
	return out
}

func safeTrim(s string, n int) string {
	if n <= 0 {
		return ""
	}
	if len(s) <= n {
		return s
	}
	cut := strings.LastIndexAny(s[:n], ".\n")
	if cut > 0 && cut >= n-400 {
		return s[:cut+1]
	}
	return s[:n]
}

func truncate(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "...(truncated)"
}

func isRetryable(err error) bool {
	msg := err.Error()
	return strings.Contains(msg, "API 400") ||
		strings.Contains(msg, "API 5") ||
		strings.Contains(msg, "index out of range") ||
		strings.Contains(msg, "Model is loading") ||
		strings.Contains(msg, "Service Unavailable")
}

func getenvDefault(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
