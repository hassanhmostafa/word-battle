import { Component } from "@angular/core";
import { Router } from "@angular/router";
import { CommonModule } from "@angular/common";
import { UserGuessesComponent } from "../user-guesses/user-guesses.component";
import { AiGuessesComponent } from "../ai-guesses/ai-guesses.component";
import { LoggingService } from "../../services/logging.service";
import { GameService } from "../../services/game.service";

@Component({
  selector: "app-game",
  standalone: true,
  imports: [CommonModule, UserGuessesComponent, AiGuessesComponent],
  templateUrl: "./game.component.html",
  styleUrls: ["./game.component.scss"],
})
export class GameComponent {
  constructor(
    private loggingService: LoggingService,
    private router: Router,
    public gameService: GameService
  ) {
    this.currentAICategory = "";

    // ✅ REFRESH GUARD: If the player refreshes the page mid-game,
    // the "new_game" flag will not be in localStorage (it is only set
    // by game-mode-selection.component.ts when "Start Game" is clicked).
    // In that case, redirect to "/" so they start a clean new game.
    const isNewGame = localStorage.getItem("new_game") === "true";
    if (!isNewGame) {
      console.log("🔄 Page refreshed mid-game — redirecting to /");
      this.router.navigate(["/"]);
      return;
    }
  }

  userGuessCategoryUsage: { [key: string]: number } = {
    animal: 0,
    food: 0,
    place: 0,
  };

  aiGuessCategoryUsage: { [key: string]: number } = {
    animal: 0,
    food: 0,
    place: 0,
  };

  currentAICategory: string;

  CATEGORY_LIMIT = 2;

  roundNumber = 1;

  // ✅ Dynamic difficulty (updated by backend)
  currentDifficulty: string = "easy1";

  // Odd rounds (1,3,5,...,11): AI describes, user guesses → isUserGuess = TRUE
  // Even rounds (2,4,6,...,12): User describes, AI guesses → isUserGuess = FALSE
  get isUserGuess(): boolean {
    return this.roundNumber % 2 === 1;
  }

  // ✅ Move to next round or end game after 12 rounds
  nextRound() {
    if (this.roundNumber < 12) {
      this.roundNumber++;
      console.log("Moving to round", this.roundNumber);
      console.log(
        `Round ${this.roundNumber}: ${
          this.isUserGuess
            ? "AI describes (user guesses)"
            : "User describes (AI guesses)"
        }`
      );

      if (!this.isUserGuess) {
        this.currentAICategory = this.getRandomCategory();
        console.log("New AI category:", this.currentAICategory);
      }
    } else {
      // ── Game finished (12 rounds completed) ──
      const userTimeLeft = this.gameService.userGuessTimeLeft;
      const aiTimeLeft = this.gameService.aiGuessTimeLeft;

      let winner: "user" | "ai" | "tie";
      if (userTimeLeft > aiTimeLeft) {
        winner = "user";
      } else if (aiTimeLeft > userTimeLeft) {
        winner = "ai";
      } else {
        winner = "tie";
      }

      console.log(
        `🏆 Game over — User time: ${userTimeLeft}s | AI time: ${aiTimeLeft}s | Winner: ${winner}`
      );

      this.loggingService.logEvent("gameFinished", {
        totalRounds: this.roundNumber,
        userStats: this.gameService.userStats,
        aiStats: this.gameService.aiStats,
        roundNumber: this.roundNumber,
        userTimeLeft,
        aiTimeLeft,
        winner,
        timestamp: new Date().toISOString(),
      });

      this.gameService
        .endGame("completed", userTimeLeft, aiTimeLeft, winner)
        .subscribe({
          next: () => {
            console.log("Game ended successfully");
          },
          error: (err) => {
            console.error("Error ending game:", err);
          },
        });

      this.playWinSound();
      this.playApplauseSound();

      this.router.navigate(["/winner"], {
        queryParams: {
          winner,
          userTime: userTimeLeft,
          aiTime: aiTimeLeft,
        },
      });
    }
  }

  // ✅ Update difficulty when received from backend
  updateDifficulty(newDifficulty: string) {
    this.currentDifficulty = newDifficulty;
    console.log("📊 Difficulty updated to:", newDifficulty);
  }

  getRandomCategory(): string {
    const categories = Object.keys(this.aiGuessCategoryUsage);
    const availableCategories = categories.filter(
      (category) => this.aiGuessCategoryUsage[category] < this.CATEGORY_LIMIT
    );
    console.log("Available categories for AI:", availableCategories);
    if (availableCategories.length === 0) {
      throw new Error("No available categories left for AI to guess.");
    }
    const randomIndex = Math.floor(Math.random() * availableCategories.length);
    const selectedCategory = availableCategories[randomIndex];
    console.log("Selected category for AI:", selectedCategory);
    this.aiGuessCategoryUsage[selectedCategory]++;
    console.log("AI category usage after selection:", this.aiGuessCategoryUsage);
    return selectedCategory;
  }

  onTimerChanged(event: {
    userGuessTimeDiff?: number;
    aiGuessTimeDiff?: number;
  }): void {
    if (event.userGuessTimeDiff !== undefined) {
      this.gameService.userGuessTimeLeft =
        this.gameService.userGuessTimeLeft + event.userGuessTimeDiff;
      console.log("User guess time left:", this.gameService.userGuessTimeLeft);

      if (this.gameService.userGuessTimeLeft <= 0) {
        const userTimeLeft = 0;
        const aiTimeLeft = this.gameService.aiGuessTimeLeft;
        const winner = "ai";

        this.gameService
          .endGame("timeout", userTimeLeft, aiTimeLeft, winner)
          .subscribe({
            next: () => {},
            error: (e) => console.warn("end-game failed:", e),
          });

        this.router.navigate(["/game-over"], {
          queryParams: {
            reason: "user-timeout",
            roundNumber: this.roundNumber,
          },
        });
        return;
      }
    }

    if (event.aiGuessTimeDiff !== undefined) {
      this.gameService.aiGuessTimeLeft =
        this.gameService.aiGuessTimeLeft + event.aiGuessTimeDiff;
      console.log("AI guess time left:", this.gameService.aiGuessTimeLeft);

      if (this.gameService.aiGuessTimeLeft <= 0 && !this.isUserGuess) {
        const userTimeLeft = this.gameService.userGuessTimeLeft;
        const aiTimeLeft = 0;
        const winner = "user";

        this.gameService
          .endGame("timeout", userTimeLeft, aiTimeLeft, winner)
          .subscribe({
            next: () => {},
            error: (e) => console.warn("end-game failed:", e),
          });

        this.router.navigate(["/game-over"], {
          queryParams: { reason: "ai-timeout", roundNumber: this.roundNumber },
        });
        return;
      }
    }
  }

  onGameOver(): void {
    const userTimeLeft = this.gameService.userGuessTimeLeft;
    const aiTimeLeft = this.gameService.aiGuessTimeLeft;

    let winner: "user" | "ai" | "tie";
    if (userTimeLeft > aiTimeLeft) {
      winner = "user";
    } else if (aiTimeLeft > userTimeLeft) {
      winner = "ai";
    } else {
      winner = "tie";
    }

    this.gameService
      .endGame("timeout", userTimeLeft, aiTimeLeft, winner)
      .subscribe({
        next: () => {},
        error: (e) => console.warn("end-game failed:", e),
      });

    this.router.navigate(["/game-over"], {
      queryParams: { reason: "timeout", roundNumber: this.roundNumber },
    });
  }

  playWinSound() {
    const audio = new Audio("assets/sounds/win.wav");
    audio.play();
  }

  playApplauseSound() {
    const audio = new Audio("assets/sounds/applause.wav");
    audio.play();
  }
}
