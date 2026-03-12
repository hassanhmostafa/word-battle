import { Injectable } from "@angular/core";
import { HttpClient } from "@angular/common/http";

@Injectable({ providedIn: "root" })
export class LoggingService {
  private endpoint = "/llm-api/log";
  private readonly PARTICIPANT_ID_KEY = 'participant_id';
  
  constructor(private http: HttpClient) {}

  /**
   * Get the participant ID from localStorage
   */
  private getParticipantId(): string | null {
    return localStorage.getItem(this.PARTICIPANT_ID_KEY);
  }

  logEvent(event: string, details: any) {
    const payload = {
      timestamp: new Date().toISOString(),
      sessionId: this.getSessionId(),
      participantId: this.getParticipantId(), // Add participant ID
      username: localStorage.getItem("username") || "Guest",
      event,
      details,
    };
    this.http.post(this.endpoint, payload).subscribe();
  }

  private getSessionId(): string {
    if (!localStorage.getItem("sessionId")) {
      localStorage.setItem("sessionId", crypto.randomUUID());
    }
    return localStorage.getItem("sessionId")!;
  }
}