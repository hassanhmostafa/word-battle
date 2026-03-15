import { Component, OnInit } from "@angular/core";
import { ActivatedRoute, Router } from "@angular/router";
import { GameService } from "../../services/game.service";
import { SoundService } from "../../services/sound.service";
import { LoggingService } from "../../services/logging.service";

@Component({
  selector: "app-game-over",
  templateUrl: "./game-over.component.html",
  styleUrls: ["./game-over.component.scss"],
})
export class GameOverComponent implements OnInit {
  reason: string | null = null;
  roundNumber: number | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    public gameService: GameService,
    private soundService: SoundService,
    private loggingService: LoggingService
  ) {}

  ngOnInit(): void {
    this.reason = this.route.snapshot.queryParamMap.get("reason");
    this.roundNumber = Number(this.route.snapshot.queryParamMap.get("roundNumber"));

    localStorage.removeItem("current_round_id");
    localStorage.removeItem("current_game_id");

    if (this.reason === "ai-timeout") {
      this.soundService.playWin();
    } else {
      this.soundService.playGameOver();
    }

    // ── Determine winner ──
    // user-timeout → ai wins (user ran out of time)
    // ai-timeout   → user wins (ai ran out of time)
    const userTimeLeft = this.gameService.userGuessTimeLeft;
    const aiTimeLeft = this.gameService.aiGuessTimeLeft;

    let winner: "user" | "ai" | "tie";
    if (this.reason === "user-timeout") {
      winner = "ai";
    } else if (this.reason === "ai-timeout") {
      winner = "user";
    } else {
      // Generic timeout or quit — whoever has more time wins
      if (userTimeLeft > aiTimeLeft) {
        winner = "user";
      } else if (aiTimeLeft > userTimeLeft) {
        winner = "ai";
      } else {
        winner = "tie";
      }
    }

    // ✅ FIX: Call endGame (not endRound) so the Games table is updated
    // with outcome, winner, user_final_time, ai_final_time
    this.gameService
      .endGame("timeout", userTimeLeft, aiTimeLeft, winner)
      .subscribe({
        next: () => {},
        error: (e) => console.warn("end-game failed:", e),
      });

    this.loggingService.logEvent("gameOver", {
      reason: this.reason,
      userStats: this.gameService.userStats,
      aiStats: this.gameService.aiStats,
      winner,
      aiTimeLeft,
      userTimeLeft,
      roundNumber: this.roundNumber,
    });
  }

  get message(): string {
    switch (this.reason) {
      case "user-timeout":
        return "⏰ Time's up! You lost this round.";
      case "ai-timeout":
        return "The AI ran out of time! You won!";
      default:
        return "Game over.";
    }
  }

  get title(): string {
    switch (this.reason) {
      case "ai-timeout":
        return "You Won!";
      default:
        return "Game Over";
    }
  }

  startGame() {
    this.loggingService.logEvent("playAgainClicked", {});
    this.gameService.resetGame();
    localStorage.removeItem("current_round_id");
    localStorage.removeItem("current_game_id");
    localStorage.setItem("new_game", "true");
    this.router.navigate(["/game"]);
  }

  backToStart() {
    this.loggingService.logEvent("backToStartClicked", { source: "game-over" });
    this.gameService.resetGame();
    localStorage.removeItem("current_round_id");
    localStorage.removeItem("current_game_id");
    localStorage.removeItem("new_game");
    window.location.href = "/";
  }
}
