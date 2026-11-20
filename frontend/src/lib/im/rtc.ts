import { Room, RoomEvent, Track } from "livekit-client";
import type { SetupDraft } from "./types";

type Control = { type: string; [key: string]: unknown };

/** Browser media uses WebRTC; the Gnani key never leaves the backend. */
export class RtcInterviewClient {
  private room = new Room({ adaptiveStream: true, dynacast: true });
  private audio = new Set<HTMLMediaElement>();
  private closed = false;

  constructor(private receive: (message: Control) => void,
              private disconnected: () => void) {
    this.room.on(RoomEvent.DataReceived, (bytes, _participant, _kind, topic) => {
      if (this.closed || topic !== "im.control") return;
      try {
        const msg = JSON.parse(new TextDecoder().decode(bytes)) as Control;
        if (msg && typeof msg.type === "string") this.receive(msg);
      } catch {
        this.receive({ type: "error", message: "Invalid RTC control message" });
      }
    });
    this.room.on(RoomEvent.TrackSubscribed, (track) => {
      if (this.closed || track.kind !== Track.Kind.Audio) return;
      const element = track.attach();
      element.autoplay = true;
      element.style.display = "none";
      document.body.appendChild(element);
      this.audio.add(element);
    });
    this.room.on(RoomEvent.TrackUnsubscribed, (track) => {
      for (const element of track.detach()) {
        element.remove();
        this.audio.delete(element);
      }
    });
    this.room.on(RoomEvent.Disconnected, () => this.disconnect());
  }

  async connect(setup: SetupDraft, track: string): Promise<string> {
    const response = await fetch("/api/rtc/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        track, language: setup.languageCode, target_questions: setup.questionTarget || 3,
        role: setup.targetRole || "Software Engineer", github_repo: setup.github || null,
        resume_text: setup.highlights || null, allow_gemini: false,
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(body.detail || "Could not prepare RTC session");
    }
    const config = await response.json() as { url: string; token: string; session_id: string };
    try {
      await this.room.connect(config.url, config.token);
      await this.room.startAudio();
      await this.room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      });
      return config.session_id;
    } catch (error) {
      this.disconnect();
      throw error;
    }
  }

  disconnect() {
    if (this.closed) return;
    this.closed = true;
    void this.room.disconnect();
    for (const element of this.audio) element.remove();
    this.audio.clear();
    this.disconnected();
  }
}
