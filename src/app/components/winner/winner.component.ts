import { Component, OnInit } from "@angular/core";
import { ActivatedRoute, Router } from "@angular/router";
import { GameService } from "../../services/game.service";
import { SoundService } from "../../services/sound.service";
import { LoggingService } from "../../services/logging.service";

@Component({
  selector: "app-game-win",
  templateUrl: "./winner.component.html",
  styleUrls: ["./winner.component.scss"],
})
export class WinnerComponent implements OnInit {
  winner: string | null = null;
  userTime: number | null = null;
  aiTime: number | null = null;

  // Resolved winner used for display — set in ngOnInit
  resolvedWinner: "user" | "ai" | "tie" = "tie";

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    public gameService: GameService,
    private soundService: SoundService,
    private loggingService: LoggingService
  ) {}

  ngOnInit(): void {
    localStorage.removeItem("current_round_id");
    localStorage.removeItem("current_game_id");

    // Read winner/times from query params (set by game.component.ts)
    this.winner = this.route.snapshot.queryParamMap.get("winner");
    this.userTime = Number(this.route.snapshot.queryParamMap.get("userTime"));
    this.aiTime = Number(this.route.snapshot.queryParamMap.get("aiTime"));

    // Fallback to gameService values if query params are missing
    const userTimeLeft = (this.userTime != null && !isNaN(this.userTime)) ? this.userTime : this.gameService.userGuessTimeLeft;
    const aiTimeLeft = (this.aiTime != null && !isNaN(this.aiTime)) ? this.aiTime : this.gameService.aiGuessTimeLeft;

    // Resolve winner: prefer query param, fall back to time comparison
    if (this.winner === "user" || this.winner === "ai" || this.winner === "tie") {
      this.resolvedWinner = this.winner;
    } else {
      if (userTimeLeft > aiTimeLeft) this.resolvedWinner = "user";
      else if (aiTimeLeft > userTimeLeft) this.resolvedWinner = "ai";
      else this.resolvedWinner = "tie";
    }

    // Play appropriate sound
    if (this.resolvedWinner === "user") {
      this.soundService.playWin();
    } else {
      this.soundService.playGameOver();
    }


    this.loggingService.logEvent("gameWin", {
      winner: this.resolvedWinner,
      aiTimeLeft,
      userTimeLeft,
      userStats: this.gameService.userStats,
    });
  }

  get title(): string {
    switch (this.resolvedWinner) {
      case "user": return "You Won! 🎉";
      case "ai":   return "AI Won!";
      case "tie":  return "It's a Tie!";
    }
  }

  get message(): string {
    switch (this.resolvedWinner) {
      case "user": return "Congratulations! You had more time left — you win!";
      case "ai":   return "The AI had more time left — better luck next time!";
      case "tie":  return "Both players finished with the same time — it's a draw!";
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
}
