import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { GameService } from './game.service';

@Injectable({
  providedIn: 'root'
})
export class CommentaryService {

  private apiUrl: string;

  constructor(private http: HttpClient, private gameService: GameService) {
    this.apiUrl = this.gameService.apiUrl;
  }

  /**
   * Fire-and-forget: requests a funny AI message.
   * Calls the callback with the message when it arrives.
   * Never blocks the game flow. Fails silently.
   */
  generate(
    event: string,
    context: Record<string, any>,
    callback: (message: string) => void
  ): void {
    this.http.post<{ message: string }>(`${this.apiUrl}/commentary`, {
      event,
      context
    }).subscribe({
      next: (res) => {
        const msg = (res?.message || '').trim();
        if (msg) {
          callback(msg);
        }
      },
      error: () => {
        // Fail silently — commentary is cosmetic
      }
    });
  }
}
