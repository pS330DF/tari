//! Minimal synchronous engine client: session control + lockstep frame submission.
//!
//! One frame in flight at a time. Frames produced while waiting are replaced
//! by newer ones at the capture side (latest-wins), so latency stays bounded.

use std::error::Error;
use std::net::TcpStream;

use serde_json::{json, Value};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{connect, Message, WebSocket};

use crate::packet::SCHEMA_VERSION;

pub type BoxError = Box<dyn Error + Send + Sync>;

#[derive(Debug, Clone, PartialEq)]
pub enum FrameOutcome {
    Result { frame_id: u64, coaching_mode: String, events: usize, recommendations: Vec<String>, engine_total_ms: Option<f64> },
    Dropped { frame_id: Option<u64>, reason: String },
}

pub struct EngineClient {
    ws: WebSocket<MaybeTlsStream<TcpStream>>,
    pub session_id: Option<String>,
    pub hello: Value,
}

impl EngineClient {
    pub fn connect(url: &str) -> Result<Self, BoxError> {
        let (mut ws, _) = connect(url)?;
        let hello = read_json(&mut ws)?;
        if hello["type"] != "hello" {
            return Err(format!("expected hello, got {}", hello["type"]).into());
        }
        Ok(Self { ws, session_id: None, hello })
    }

    pub fn start_session(&mut self, source_id: &str, source_kind: &str, label: &str) -> Result<String, BoxError> {
        let msg = json!({
            "schema_version": SCHEMA_VERSION,
            "type": "start_session",
            "source": { "source_id": source_id, "source_kind": source_kind, "label": label },
        });
        self.ws.send(Message::Text(msg.to_string().into()))?;
        loop {
            let m = read_json(&mut self.ws)?;
            match m["type"].as_str() {
                Some("session_started") => {
                    let id = m["session_id"].as_str().unwrap_or_default().to_string();
                    self.session_id = Some(id.clone());
                    return Ok(id);
                }
                Some("notice") if m["level"] == "error" => return Err(format!("engine refused session: {}", m["message"]).into()),
                _ => continue,
            }
        }
    }

    pub fn send_frame(&mut self, packet: Vec<u8>) -> Result<(), BoxError> {
        self.ws.send(Message::Binary(packet.into()))?;
        Ok(())
    }

    /// Read engine messages until the outcome for `frame_id` arrives.
    pub fn wait_outcome(&mut self, frame_id: u64) -> Result<FrameOutcome, BoxError> {
        loop {
            let m = read_json(&mut self.ws)?;
            match m["type"].as_str() {
                Some("frame_result") if m["perception"]["frame_id"].as_u64() == Some(frame_id) => {
                    let recs = m["recommendations"]
                        .as_array()
                        .map(|a| a.iter().filter_map(|r| r["rule_id"].as_str().map(String::from)).collect())
                        .unwrap_or_default();
                    return Ok(FrameOutcome::Result {
                        frame_id,
                        coaching_mode: m["state"]["coaching_mode"].as_str().unwrap_or("unknown").to_string(),
                        events: m["events"].as_array().map(|a| a.len()).unwrap_or(0),
                        recommendations: recs,
                        engine_total_ms: m["timings_ms"]["engine_total_ms"].as_f64(),
                    });
                }
                Some("frame_dropped") if m["frame_id"].as_u64() == Some(frame_id) || m["frame_id"].is_null() => {
                    return Ok(FrameOutcome::Dropped {
                        frame_id: m["frame_id"].as_u64(),
                        reason: m["reason"].as_str().unwrap_or("unknown").to_string(),
                    });
                }
                Some("notice") => eprintln!("[engine notice] {}", m["message"]),
                _ => continue,
            }
        }
    }

    pub fn end_session(&mut self) -> Result<Value, BoxError> {
        let msg = json!({ "schema_version": SCHEMA_VERSION, "type": "end_session", "reason": "capture_stopped" });
        self.ws.send(Message::Text(msg.to_string().into()))?;
        loop {
            let m = read_json(&mut self.ws)?;
            if m["type"] == "session_ended" {
                return Ok(m["summary"].clone());
            }
        }
    }
}

fn read_json(ws: &mut WebSocket<MaybeTlsStream<TcpStream>>) -> Result<Value, BoxError> {
    loop {
        match ws.read()? {
            Message::Text(t) => return Ok(serde_json::from_str(t.as_str())?),
            Message::Close(_) => return Err("engine closed the connection".into()),
            _ => continue,
        }
    }
}
