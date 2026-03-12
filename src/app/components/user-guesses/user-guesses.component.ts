import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { Component, OnInit, OnDestroy, Input, Output, EventEmitter, OnChanges, SimpleChanges } from "@angular/core";
import { Router } from "@angular/router";
import { GameService, INITIAL_TIME } from "../../services/game.service";
import { GameHeaderComponent } from "../shared/game-header/game-header.component";
import { CategoryComponent } from "../category/category.component";
import { LoggingService } from "../../services/logging.service";
import { SoundService } from "../../services/sound.service";
import { CommentaryService } from "../../services/commentary.service";

@Component({
  selector: "app-user-guesses",
  standalone: true,
  imports: [CommonModule, FormsModule, GameHeaderComponent, CategoryComponent],
  templateUrl: "./user-guesses.component.html",
  styleUrls: ["./user-guesses.component.scss"],
})
export class UserGuessesComponent implements OnInit, OnDestroy, OnChanges {
  description = "";
  userGuess = "";
  correctWord = "";
  hints: string[] = [];
  feedback = "";
  isCorrect = false;
  isIncorrect = false;

  @Input() currentCategory: string = "";
  @Input() categoryUsage: { [key: string]: number } = {
    Animals: 0,
    Food: 0,
    Places: 0,
  };
  isLoading = false;
  @Input() currentDifficulty = "";
  @Input() userGuessTimeLeft = INITIAL_TIME;
  @Input() aiGuessTimeLeft = INITIAL_TIME;
  @Input() isAiGuessMode: boolean = false;

  @Output() timerChanged = new EventEmitter<{
    userGuessTimeDiff?: number;
    aiGuessTimeDiff?: number;
  }>();
  @Output() roundCompleted = new EventEmitter<void>();
  @Output() difficultyChanged = new EventEmitter<string>();

  // ── TIMER ──
  private userGuessTimer: any = null;
  timer: any; // legacy alias kept for safety

  gameOver = false;
  username = localStorage.getItem("username") || "Guest";
  hintUsed = 0;
  localWrongGuesses = 0;
  hintGivenThisRound: boolean = false;

  @Input() roundNumber: number = 1;

  // Duration tracking
  private guessStartTime: number = 0;

  // Track whether endRound was already called for this round
  roundEnded: boolean = false;

  // Prevents double-clicking Submit Guess while waiting for response
  isSubmitting: boolean = false;

  // Commentary — top bubble (round start, skip, hint)
  commentaryMessage: string = "";
  commentaryType: 'positive' | 'negative' | 'neutral' | 'warning' = 'neutral';

  // Commentary — inline with feedback (correct/wrong guess reactions)
  feedbackCommentary: string = "";
  feedbackCommentaryType: 'positive' | 'negative' | 'neutral' | 'warning' = 'neutral';

  constructor(
    public gameService: GameService,
    private router: Router,
    private loggingService: LoggingService,
    private soundService: SoundService,
    private commentaryService: CommentaryService
  ) {}

  ngOnInit() {
    this.startNewRound();
  }

  ngOnDestroy() {
    this.pauseTimer();
  }

  ngOnChanges(changes: SimpleChanges) {
    if (changes['roundNumber'] && !changes['roundNumber'].firstChange) {
      console.log("UserGuesses: roundNumber changed to", this.roundNumber, "- starting new round");
      this.startNewRound();
    }
  }

  // ── Commentary helpers ──

  private showCommentary(msg: string, type: 'positive' | 'negative' | 'neutral' | 'warning') {
    this.commentaryMessage = msg;
    this.commentaryType = type;
    setTimeout(() => {
      if (this.commentaryMessage === msg) this.commentaryMessage = "";
    }, 5000);
  }

  private showFeedbackCommentary(msg: string, type: 'positive' | 'negative' | 'neutral' | 'warning') {
    this.feedbackCommentary = msg;
    this.feedbackCommentaryType = type;
    setTimeout(() => {
      if (this.feedbackCommentary === msg) this.feedbackCommentary = "";
    }, 6000);
  }

  // ── Timer: only USER's clock runs in this mode ──

  startTimer() {
    if (this.userGuessTimer) clearInterval(this.userGuessTimer);

    this.userGuessTimer = setInterval(() => {
      if (this.userGuessTimeLeft > 0) {
        // Tick the USER's clock down by 1 second
        this.timerChanged.emit({ userGuessTimeDiff: -1 });
      } else {
        clearInterval(this.userGuessTimer);
        this.userGuessTimer = null;
        this.gameOver = true;

        if (!this.roundEnded) {
          this.roundEnded = true;
          this.gameService.endRound("timeout").subscribe({
            next: () => {},
            error: (e) => console.warn("end-round failed:", e),
          });
        }

        this.loggingService.logEvent("timeout", {
          roundNumber: this.roundNumber,
          category: this.currentCategory,
        });
      }
    }, 1000);

    this.timer = this.userGuessTimer;
  }

  pauseTimer() {
    if (this.userGuessTimer) {
      clearInterval(this.userGuessTimer);
      this.userGuessTimer = null;
    }
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  // ── Percentage-based time bonus ──
  // Returns seconds to add when a correct guess is made.
  // Bonus = 75% of the time taken to guess, clamped between 5s and 45s.
  private calcBonus(durationMs: number): number {
    const secondsTaken = durationMs / 1000;
    const bonus = Math.round(secondsTaken * 0.75);
    return Math.max(5, Math.min(45, bonus));
  }

  // ── Round logic ──

  getCurrentDifficulty(): string {
    return this.currentDifficulty || "easy1";
  }

  onCategorySelected(category: string) {
    this.currentCategory = category;
    this.pauseTimer();
    this.startNewRound();
  }

  startNewRound(isFromSkip: boolean = false) {
    this.pauseTimer();

    // Reset all state
    this.description = "";
    this.hints = [];
    this.hintUsed = 0;
    this.hintGivenThisRound = false;
    this.feedback = "";
    this.isCorrect = false;
    this.isIncorrect = false;
    this.localWrongGuesses = 0;
    this.gameOver = false;
    this.roundEnded = false;
    this.isSubmitting = false;  // reset lock on new round
    this.commentaryMessage = "";
    this.feedbackCommentary = "";

    this.isLoading = true;

    this.gameService.startGame(this.currentCategory).subscribe((response) => {
      this.description = response.description;
      this.correctWord = response.answer;
      this.isLoading = false;

      if (response.current_difficulty && response.current_difficulty !== this.currentDifficulty) {
        this.difficultyChanged.emit(response.current_difficulty);
      }

      this.guessStartTime = Date.now();

      // ── Start USER's timer only: user is guessing, so user's clock runs ──
      this.startTimer();

      this.commentaryService.generate(
        "New round started. The AI described a word and the user must guess it.",
        { round: this.roundNumber, category: this.currentCategory },
        (msg) => this.showCommentary(msg, 'neutral')
      );

      if (!isFromSkip) {
        this.loggingService.logEvent("newRoundStarted", {
          roundNumber: this.roundNumber,
          phase: "user-guess",
          category: this.currentCategory,
          difficulty: this.getCurrentDifficulty(),
          description: this.description,
          timeLeft: this.userGuessTimeLeft,
          wasSkipped: isFromSkip,
          descriptionWordCount: response.description.trim().split(/\s+/).length,
        });
      }
    });
  }

  submitGuess() {
    const guess = (this.userGuess ?? "").trim().toLowerCase();

    if (!guess) return;

    if (!this.correctWord) {
      this.feedback = "No answer loaded yet - click Change Word / wait a moment.";
      this.isIncorrect = true;
      return;
    }

    const roundId = this.gameService.getCurrentRoundId();
    if (!roundId) {
      this.feedback = "Game not ready yet - start a new round.";
      this.isIncorrect = true;
      return;
    }

    const durationMs = Date.now() - this.guessStartTime;

    // Guard: ignore if already waiting for a response
    if (this.isSubmitting) return;

    // Lock the button immediately
    this.isSubmitting = true;

    // Pause timer while processing guess
    this.pauseTimer();

    // Clear previous feedback commentary
    this.feedbackCommentary = "";

    this.gameService.checkGuess(roundId, guess, durationMs).subscribe({
      next: (res) => {
        const isCorrect = !!res?.is_correct;

        if (isCorrect) {
          if (!this.roundEnded) {
            this.roundEnded = true;
            this.gameService.endRound("win").subscribe({
              next: (response) => {
                if (response?.next_difficulty) {
                  this.difficultyChanged.emit(response.next_difficulty);
                }
              },
              error: (e) => console.warn("end-round failed:", e),
            });
          }

          this.loggingService.logEvent("userGuessSubmitted", {
            guess,
            isCorrect: true,
            roundNumber: this.roundNumber,
            phase: "user-guess",
            category: this.currentCategory,
            difficulty: this.currentDifficulty,
            guessCount: this.localWrongGuesses + 1,
            hintUsed: this.hintUsed,
            hintGivenThisRound: this.hintGivenThisRound,
          });

          this.gameService.userStats.correct++;
          this.soundService.playCorrect();

          // ── Percentage-based bonus: 75% of time taken, clamped 5s–45s ──
          const bonus = this.calcBonus(durationMs);
          this.timerChanged.emit({ userGuessTimeDiff: bonus });

          this.feedback = `Correct! +${bonus} seconds`;
          this.isCorrect = true;
          this.isIncorrect = false;

          this.commentaryService.generate(
            "The player guessed the word correctly!",
            { word: this.correctWord, category: this.currentCategory, attempt: this.localWrongGuesses + 1 },
            (msg) => this.showFeedbackCommentary(msg, 'positive')
          );

          // Wait 4.5s so user can read feedback + commentary before advancing
          setTimeout(() => {
            this.currentCategory = "";
            this.roundCompleted.emit();
          }, 4500);

        } else {
          this.loggingService.logEvent("userGuessSubmitted", {
            guess,
            isCorrect: false,
            roundNumber: this.roundNumber,
            phase: "user-guess",
            category: this.currentCategory,
            difficulty: this.currentDifficulty,
            guessCount: this.localWrongGuesses + 1,
            hintUsed: this.hintUsed,
            hintGivenThisRound: this.hintGivenThisRound,
          });

          this.localWrongGuesses++;
          this.gameService.userStats.wrong++;
          this.soundService.playWrong();

          this.isCorrect = false;
          this.isIncorrect = true;

          // Wrong guess: user loses 5 seconds
          this.timerChanged.emit({ userGuessTimeDiff: -5 });

          if (this.localWrongGuesses >= 3) {
            if (!this.roundEnded) {
              this.roundEnded = true;
              this.gameService.endRound("loss").subscribe({
                next: (response) => {
                  if (response?.next_difficulty) {
                    this.difficultyChanged.emit(response.next_difficulty);
                  }
                },
                error: (e) => console.warn("end-round failed:", e),
              });
            }

            this.loggingService.logEvent("revealAnswer", {
              correctAnswer: this.correctWord,
              roundNumber: this.roundNumber,
              category: this.currentCategory,
              phase: "user-guess",
              hintUsed: this.hintUsed,
            });

            this.feedback = "You have used all your guesses! The correct word was: " + this.correctWord;

            this.commentaryService.generate(
              "The player used all 3 guesses and failed to guess the word.",
              { word: this.correctWord, category: this.currentCategory },
              (msg) => this.showFeedbackCommentary(msg, 'negative')
            );

            // Wait 4.5s so user can read feedback + commentary before advancing
            setTimeout(() => {
              this.currentCategory = "";
              this.roundCompleted.emit();
            }, 4500);

          } else {
            this.feedback = "Wrong! Try again. -5 seconds";

            this.commentaryService.generate(
              "The player guessed wrong. They have more attempts left.",
              { guess, category: this.currentCategory, attempt: this.localWrongGuesses },
              (msg) => this.showFeedbackCommentary(msg, 'warning')
            );

            // Unlock the button — player still has attempts left
            this.isSubmitting = false;

            // Resume timer for next attempt
            this.guessStartTime = Date.now();
            this.startTimer();
          }
        }

        this.userGuess = "";
      },

      error: (e) => {
        // Unlock on error too
        this.isSubmitting = false;
        console.warn("checkGuess failed:", e);
        this.feedback = "Could not validate your guess. Try again.";
        this.isCorrect = false;
        this.isIncorrect = true;
        this.userGuess = "";
        this.guessStartTime = Date.now();
        this.startTimer();
      },
    });
  }

  getHint() {
    this.hintUsed++;
    this.pauseTimer();

    this.commentaryService.generate(
      "The player is requesting a hint from the AI.",
      { category: this.currentCategory, hints_used: this.hintUsed },
      (msg) => this.showCommentary(msg, 'neutral')
    );

    this.gameService.getHint(this.correctWord).subscribe((response) => {
      this.hints.push(response.hint);
      this.feedback = `Hint: ${response.hint}`;
      this.hintGivenThisRound = true;

      // Hint costs the USER 2 seconds (user is the one guessing)
      this.timerChanged.emit({ userGuessTimeDiff: -2 });

      this.startTimer();

      this.loggingService.logEvent("hintUsed", {
        roundNumber: this.roundNumber,
        category: this.currentCategory,
        difficulty: this.currentDifficulty,
        phase: "user-guess",
        word: this.correctWord,
        hintUsed: this.hintUsed,
        hintDescription: response.hint,
        hintWordCount: response.hint.trim().split(/\s+/).length,
      });
    });
  }

  handleSkip() {
    this.timerChanged.emit({ userGuessTimeDiff: -2 });
    this.gameService.userStats.skipped++;

    this.loggingService.logEvent("userSkippedWord", {
      roundNumber: this.roundNumber,
      difficulty: this.currentDifficulty,
      category: this.currentCategory,
      reason: "user_clicked_change_word",
    });

    this.commentaryService.generate(
      "The player decided to skip this word and get a new one.",
      { round: this.roundNumber },
      (msg) => this.showCommentary(msg, 'neutral')
    );

    this.startNewRound(true);
  }

  goBack() {
    if (!this.roundEnded) {
      this.roundEnded = true;
      this.gameService.endRound("quit").subscribe({
        next: () => {},
        error: () => {},
      });
    }
    window.location.href = "/llm-wordgame/";
  }

  nextRound() {
    this.roundCompleted.emit();
  }
}
