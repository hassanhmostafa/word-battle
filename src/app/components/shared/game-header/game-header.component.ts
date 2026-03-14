import { Component, Input } from "@angular/core";
import { CommonModule } from "@angular/common";
import { INITIAL_TIME } from "../../../services/game.service";


@Component({
  selector: "app-game-header",
  standalone: true,
  imports: [CommonModule],
  templateUrl: "./game-header.component.html",
  styleUrls: ["./game-header.component.scss"],
})
export class GameHeaderComponent {
  @Input() username: string = "";
  @Input() round: number = 1;
  @Input() difficulty: string = "";
  @Input() correctAnswers: number = 0;
  @Input() wrongAnswers: number = 0;
  @Input() userTimeLeft: number = 0;
  @Input() aiTimeLeft: number = 0;
  @Input() currentCategory: string = "";
  @Input() userStats!: { correct: number; wrong: number; skipped: number };
  @Input() aiStats!: { correct: number; wrong: number; skipped: number };
  @Input() isAiGuessMode: boolean = false;

  // Number of wrong guesses in the current round — passed from child component
  @Input() wrongGuesses: number = 0;

  // The maximum time each player starts with.
  // The arc is calculated as a fraction of this value.
  @Input() maxTime: number = INITIAL_TIME;

  // SVG circle circumference for r=34: 2 * π * 34 ≈ 213.6
  private readonly CIRCUMFERENCE = 213.6;

  get displayRound(): number {
    const safeRound = Math.max(1, this.round || 1);
    return this.isAiGuessMode ? Math.floor((safeRound + 1) / 2) : Math.ceil(safeRound / 2);
  }

  getUserArcOffset(): number {
    return this.calcOffset(this.userTimeLeft);
  }

  getAiArcOffset(): number {
    return this.calcOffset(this.aiTimeLeft);
  }

  private calcOffset(timeLeft: number): number {
    const ratio = Math.max(0, Math.min(timeLeft, this.maxTime)) / this.maxTime;
    return this.CIRCUMFERENCE * (1 - ratio);
  }
}
