import { Injectable } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import { Observable, throwError } from "rxjs";
import { tap } from "rxjs/operators";
export const INITIAL_TIME = 150;

interface GameResponse {
  current_difficulty: string;
  description: string;
  answer: string;
  round_id: number;
  game_id: number;
  round_number: number;
  participant_id: string;
  referee_ok: boolean;
  violations: any[];
}

interface GuessResponse {
  is_correct: boolean;
  guess: string;
}

interface HintResponse {
  hint: string;
}

interface EndGameResponse {
  next_difficulty: any;
  status: string;
  game_ended?: boolean;
  rounds_completed?: number;
  rounds_remaining?: number;
  winner?: string;
}

interface CheckGuessResponse {
  is_correct: boolean;
}

@Injectable({
  providedIn: "root",
})
export class GameService {
  public apiUrl = "/llm-api";
  private readonly PARTICIPANT_ID_KEY = "participant_id";
  private readonly ROUND_ID_KEY = "current_round_id";
  private readonly GAME_ID_KEY = "current_game_id";
  private readonly DIFFICULTY_KEY = "game_difficulty";
  participantId: string | null = localStorage.getItem("participant_id");
  username: string = localStorage.getItem("username") || "Guest";
  currentCategory: string = "animal";

  constructor(private http: HttpClient) {}

  private getParticipantId(): string | null {
    return localStorage.getItem(this.PARTICIPANT_ID_KEY);
  }

  private setParticipantId(participantId: string): void {
    localStorage.setItem(this.PARTICIPANT_ID_KEY, participantId);
  }

  getCurrentRoundId(): number | null {
    const roundId = localStorage.getItem(this.ROUND_ID_KEY);
    return roundId ? parseInt(roundId, 10) : null;
  }

  private setCurrentRoundId(roundId: number): void {
    localStorage.setItem(this.ROUND_ID_KEY, roundId.toString());
  }

  getCurrentGameId(): number | null {
    const gameId = localStorage.getItem(this.GAME_ID_KEY);
    return gameId ? parseInt(gameId, 10) : null;
  }

  private setCurrentGameId(gameId: number): void {
    localStorage.setItem(this.GAME_ID_KEY, gameId.toString());
  }

  getDifficulty(): string {
    return localStorage.getItem(this.DIFFICULTY_KEY) || "easy1";
  }

  setDifficulty(difficulty: string): void {
    localStorage.setItem(this.DIFFICULTY_KEY, difficulty);
  }

  startGame(category: string = this.currentCategory): Observable<any> {
    const isNewGame = localStorage.getItem("new_game") === "true";

    const body: any = {
      category,
      participant_id: this.participantId,
      username: this.username,
      new_game: isNewGame,
    };

    if (isNewGame) {
      localStorage.removeItem("new_game");
      console.log("🆕 Starting NEW game (new_game=true sent to backend)");
    }

    return this.http.post<any>(`${this.apiUrl}/start`, body).pipe(
      tap((res) => {
        if (res.round_id) {
          localStorage.setItem("current_round_id", res.round_id.toString());
        }
        if (res.game_id) {
          localStorage.setItem("current_game_id", res.game_id.toString());
        }
        if (res.participant_id) {
          this.participantId = res.participant_id;
          localStorage.setItem("participant_id", res.participant_id);
        }
      })
    );
  }

  checkGuess(
    roundId: number,
    guess: string,
    durationMs?: number
  ): Observable<CheckGuessResponse> {
    return this.http.post<CheckGuessResponse>(`${this.apiUrl}/check-guess`, {
      round_id: roundId,
      guess,
      duration_ms: durationMs,
    });
  }

  userStats = { correct: 0, wrong: 0, skipped: 0 };
  aiStats = { correct: 0, wrong: 0, skipped: 0 };
  userGuessTimeLeft = INITIAL_TIME;
  aiGuessTimeLeft = INITIAL_TIME;

  resetGame() {
    this.resetStats();
    this.userGuessTimeLeft = INITIAL_TIME;
    this.aiGuessTimeLeft = INITIAL_TIME;
  }

  resetStats() {
    this.userStats = { correct: 0, wrong: 0, skipped: 0 };
    this.aiStats = { correct: 0, wrong: 0, skipped: 0 };
  }

  makeGuess(
    text: string,
    secretWord: string,
    category: string,
    difficulty: string,
    forbiddenWords: string[],
    durationMs?: number,
    descriptionApproved: boolean = false
  ): Observable<GuessResponse> {
    const roundId = this.getCurrentRoundId();
    return this.http.post<GuessResponse>(`${this.apiUrl}/guess`, {
      round_id: roundId,
      description: text,
      secret_word: secretWord,
      category,
      difficulty,
      forbidden_words: forbiddenWords,
      duration_ms: durationMs,
      description_approved: descriptionApproved,
    });
  }

  validateDescription(
    text: string,
    secretWord: string,
    category: string,
    difficulty: string,
    forbiddenWords: string[],
    durationMs?: number
  ): Observable<{ valid: boolean }> {
    const roundId = this.getCurrentRoundId();
    return this.http.post<{ valid: boolean }>(`${this.apiUrl}/validate-description`, {
      round_id: roundId,
      description: text,
      secret_word: secretWord,
      category,
      difficulty,
      forbidden_words: forbiddenWords,
      duration_ms: durationMs,
    });
  }

  getForbiddenWords(
    word: string,
    category: string
  ): Observable<{ forbidden_words: string[] }> {
    const roundId = this.getCurrentRoundId();

    return this.http.post<{ forbidden_words: string[] }>(
      `${this.apiUrl}/get-forbidden-words`,
      {
        word,
        category,
        round_id: roundId,
      }
    );
  }

  getHint(word: string): Observable<HintResponse> {
    const participantId = this.getParticipantId();
    const roundId = this.getCurrentRoundId();
    const difficulty = this.getDifficulty();

    return this.http.post<HintResponse>(`${this.apiUrl}/hint`, {
      word,
      difficulty,
      participant_id: participantId,
      round_id: roundId,
    });
  }

  fetchWord(category: string = this.currentCategory): Observable<any> {
    const isNewGame = localStorage.getItem("new_game") === "true";

    const body: any = {
      category,
      difficulty: "easy1",
      participant_id: this.participantId,
      username: this.username,
      new_game: isNewGame,
    };

    if (isNewGame) {
      localStorage.removeItem("new_game");
      console.log("🆕 Starting NEW game (new_game=true sent to backend)");
    }

    return this.http.post<any>(`${this.apiUrl}/get-word`, body).pipe(
      tap((res) => {
        if (res.round_id) {
          localStorage.setItem("current_round_id", res.round_id.toString());
        }
        if (res.game_id) {
          localStorage.setItem("current_game_id", res.game_id.toString());
        }
        if (res.participant_id) {
          this.participantId = res.participant_id;
          localStorage.setItem("participant_id", res.participant_id);
        }
      })
    );
  }

  // ✅ NEW: Request AI to generate a valid description for the current round's word.
  // Called after the user submits 3 violated descriptions in a row.
  // Passes the existing forbidden_words so the backend uses the same list
  // the player already saw — no inconsistency.
  generateDescription(roundId: number, forbiddenWords: string[] = []): Observable<{ description: string }> {
    return this.http.post<{ description: string }>(
      `${this.apiUrl}/generate-description`,
      { round_id: roundId, forbidden_words: forbiddenWords }
    );
  }

  // ✅ End a single round — only updates the Rounds table (outcome, ended_at)
  endRound(outcome: "win" | "loss" | "timeout" | "quit"): Observable<EndGameResponse> {
    const roundId = this.getCurrentRoundId();
    if (!roundId) {
      return throwError(() => new Error("No current round_id found in localStorage"));
    }
    return this.http.post<EndGameResponse>(`${this.apiUrl}/end-game`, {
      round_id: roundId,
      outcome,
    });
  }

  // ✅ End the full game session — updates the Games table with winner, final times, outcome
  endGame(
    outcome: string,
    userTimeLeft?: number,
    aiTimeLeft?: number,
    winner?: string
  ): Observable<any> {
    const gameId = this.getCurrentGameId();

    if (outcome === "quit") {
      winner = "ai";
    }

    if (!winner && userTimeLeft !== undefined && aiTimeLeft !== undefined) {
      if (userTimeLeft > aiTimeLeft) {
        winner = "user";
      } else if (aiTimeLeft > userTimeLeft) {
        winner = "ai";
      } else {
        winner = "tie";
      }
    }

    return this.http.post<any>(`${this.apiUrl}/end-game`, {
      game_id: gameId,
      outcome,
      user_time_left: userTimeLeft,
      ai_time_left: aiTimeLeft,
      winner,
    });
  }
}
