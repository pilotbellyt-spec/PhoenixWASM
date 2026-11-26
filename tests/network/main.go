// This Linux guest exercises the same DNS, TCP and certificate store as Phoenix.
package main

import (
	"bufio"
	"crypto/rand"
	"crypto/sha1"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

func check() error {
	client := &http.Client{Timeout: 30 * time.Second}
	r, err := client.Get("https://discord.com/api/v9/gateway")
	if err != nil {
		return err
	}
	defer r.Body.Close()
	var gateway struct{ URL string }
	if err := json.NewDecoder(r.Body).Decode(&gateway); err != nil {
		return err
	}
	if r.StatusCode != http.StatusOK || gateway.URL != "wss://gateway.discord.gg" {
		return fmt.Errorf("gateway discovery returned %s, URL %q", r.Status, gateway.URL)
	}
	fmt.Println("Discord HTTPS gateway discovery passed")

	const host = "gateway.discord.gg"
	conn, err := tls.Dial("tcp", host+":443", &tls.Config{ServerName: host})
	if err != nil {
		return err
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(20 * time.Second))
	var nonce [16]byte
	if _, err := rand.Read(nonce[:]); err != nil {
		return err
	}
	key := base64.StdEncoding.EncodeToString(nonce[:])
	req, err := http.NewRequest("GET", "https://"+host+"/?v=10&encoding=json", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	req.Header.Set("Sec-WebSocket-Version", "13")
	req.Header.Set("Sec-WebSocket-Key", key)
	if err := req.Write(conn); err != nil {
		return err
	}
	upgrade, err := http.ReadResponse(bufio.NewReader(conn), req)
	if err != nil {
		return err
	}
	defer upgrade.Body.Close()
	accept := sha1.Sum([]byte(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
	if upgrade.StatusCode != http.StatusSwitchingProtocols ||
		upgrade.Header.Get("Sec-WebSocket-Accept") != base64.StdEncoding.EncodeToString(accept[:]) {
		return fmt.Errorf("gateway WebSocket upgrade failed: %s", upgrade.Status)
	}
	fmt.Println("Discord TLS WebSocket upgrade passed")
	return nil
}

func main() {
	if err := check(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
