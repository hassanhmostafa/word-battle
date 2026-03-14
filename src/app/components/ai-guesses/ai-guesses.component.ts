import { Component, OnInit, OnDestroy, OnChanges, Input, Output, EventEmitter } from "@angular/core";
import { EMPTY } from "rxjs";
import { switchMap, map } from "rxjs/operators";
import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { GameService, INITIAL_TIME } from "../../services/game.service";
import { GameHeaderComponent } from "../shared/game-header/game-header.component";
import { LoggingService } from "../../services/logging.service";
import { SoundService } from "../../services/sound.service";
import { CommentaryService } from "../../services/commentary.service";

@Component({
  selector: "app-ai-guesses",
  standalone: true,
  imports: [CommonModule, FormsModule, GameHeaderComponent],
  templateUrl: "./ai-guesses.component.html",
  styleUrls: ["./ai-guesses.component.scss"],
})
export class AiGuessesComponent implements OnInit, OnDestroy, OnChanges {
  @Input() isAiGuessMode: boolean = false;
  @Input() currentCategory: string = "animal";
  @Input() roundNumber: number = 1;
  @Input() currentDifficulty = "";
  @Input() userGuessTimeLeft = INITIAL_TIME;
  @Input() aiGuessTimeLeft = INITIAL_TIME;

  @Output() timerChanged = new EventEmitter<{
    userGuessTimeDiff?: number;
    aiGuessTimeDiff?: number;
  }>();
  @Output() gameOverEvent = new EventEmitter<void>();
  @Output() roundCompleted = new EventEmitter<void>();
  @Output() difficultyChanged = new EventEmitter<string>();

  // UI state
  isThinking: boolean = false;
  isHintPhase: boolean = false;

  // Hint usage
  hintUsed: number = 0;

  // Correctness state
  isAiGuessCorrect = false;
  aiGuessChecked = false;

  // Round inputs/outputs
  userDescription = "";
  userHint = "";
  aiGuess = "";
  feedback = "";

  // Referee UI
  refereeErrorMsg = "";
  refereeViolations: string[] = [];

  // ── TIMER ──
  timer: any = null;

  username = localStorage.getItem("username") || "Guest";

  correctWord = "";
  gameOver = false;
  localWrongGuesses = 0;
  descriptionApproved = false;

  // Violation tracking
  localUncompliantCount = 0;
  private readonly MAX_UNCOMPLIANT = 3;

  // Whether AI has taken over describing (after 3 violations)
  aiDescriptionOverride = false;
  aiGeneratedDescription = "";
  isGeneratingAiDescription = false;

  forbiddenWords: string[] = [];
  isForbiddenLoading = false;

  // Token to prevent stale async responses overwriting UI
  private guessReqId = 0;

  // Duration tracking
  private descriptionStartTime: number = 0;

  // Track whether endRound was already called for this round
  private roundEnded: boolean = false;

  // Track if round result is being shown (waiting before advancing)
  showingResult: boolean = false;

  // Commentary — single shared slot for all comment types
  commentaryMessage: string = "";
  commentaryType: 'positive' | 'negative' | 'neutral' | 'warning' = 'neutral';

  constructor(
    public gameService: GameService,
    private loggingService: LoggingService,
    private soundService: SoundService,
    private commentaryService: CommentaryService
  ) {}

  ngOnInit() {
    this.fetchWordForUserToDescribe();
    this.logStartRound();
  }

  ngOnDestroy() {
    this.pauseTimer();
  }

  ngOnChanges(changes: any) {
    if (changes.roundNumber && !changes.roundNumber.firstChange) {
      console.log("AiGuesses: roundNumber changed to", this.roundNumber, "- fetching new word");
      this.fetchWordForUserToDescribe();
      this.logStartRound();
    }
  }

  // ── Commentary helpers ──

  private showCommentary(msg: string, type: 'positive' | 'negative' | 'neutral' | 'warning', durationMs: number = 5000) {
    this.commentaryMessage = msg;
    this.commentaryType = type;
    setTimeout(() => {
      if (this.commentaryMessage === msg) this.commentaryMessage = "";
    }, durationMs);
  }

  private showFeedbackCommentary(msg: string, type: 'positive' | 'negative' | 'neutral' | 'warning') {
    this.showCommentary(msg, type, 6000);
  }

  // ── Timer ──

  pauseTimer() {
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
    const bonus = Math.round(secondsTaken * 0.5);
    return bonus;
  }

  // ── Round logic ──

  fetchWordForUserToDescribe(): void {
    this.isThinking = true;
    this.resetStateForNextWord();

    this.gameService.fetchWord(this.currentCategory).subscribe({
      next: (response) => {
        this.correctWord = response.word;

        if (response.category) this.currentCategory = response.category;
        if (response.difficulty) this.currentDifficulty = response.difficulty;

        if (response.current_difficulty && response.current_difficulty !== this.currentDifficulty) {
          this.difficultyChanged.emit(response.current_difficulty);
        }

        this.isForbiddenLoading = true;
        this.forbiddenWords = [];

        this.gameService.getForbiddenWords(this.correctWord, this.currentCategory).subscribe({
          next: (fwRes) => {
            this.forbiddenWords = (fwRes?.forbidden_words || []).map((w: string) => w.toLowerCase());
            this.isForbiddenLoading = false;
          },
          error: (e) => {
            console.error("Failed to load forbidden words", e);
            this.forbiddenWords = [];
            this.isForbiddenLoading = false;
          },
        });

        this.isThinking = false;
        this.descriptionStartTime = Date.now();

        this.commentaryService.generate(
          "New round started. The user must describe a word for the AI to guess.",
          { round: this.roundNumber, category: this.currentCategory },
          (msg) => this.showCommentary(msg, 'neutral')
        );
      },
      error: (err) => {
        console.error("Failed to fetch word", err);
        this.isThinking = false;
        this.correctWord = "";
        this.forbiddenWords = [];
        this.isForbiddenLoading = false;
        this.feedback = "Failed to fetch a word. Please try again.";
      },
    });
  }

  submitDescription() {
    const wordCount = this.userDescription.trim().split(/\s+/).filter(Boolean).length;
    if (wordCount < 3) {
      this.feedback = "Please write at least 3 words in your description.";
      return;
    }

    const durationMs = Date.now() - this.descriptionStartTime;

    this.isThinking = true;
    this.isHintPhase = false;

    this.loggingService.logEvent("aiGuessRoundStarted", {
      roundNumber: this.roundNumber,
      difficulty: this.currentDifficulty,
      description: this.userDescription,
      word: this.correctWord,
      phase: "ai-guess",
      wordCount,
    });

    this.makeAiGuess(this.userDescription, durationMs);
  }

  submitHint() {
    if (!this.userHint.trim()) return;

    this.hintUsed++;

    this.loggingService.logEvent("hintProvidedByUser", {
      roundNumber: this.roundNumber,
      difficulty: this.currentDifficulty,
      phase: "ai-guess",
      hint: this.userHint,
      wordCount: this.userHint.trim().split(/\s+/).filter(Boolean).length,
    });

    const enhancedInput = this.userDescription + " HINT: " + this.userHint;

    this.commentaryService.generate(
      "The user is giving the AI a hint because it couldn't guess the word.",
      { category: this.currentCategory, attempt: this.localWrongGuesses },
      (msg) => this.showCommentary(msg, 'neutral')
    );

    this.makeAiGuess(enhancedInput, undefined, true);
    this.userHint = "";
  }

  // Called when AI takes over describing (after 3 violations).
  submitAiGeneratedDescription() {
    if (!this.aiGeneratedDescription) return;

    this.isThinking = true;
    const requestStartTime = Date.now();
    const reqId = ++this.guessReqId;

    this.gameService
      .makeGuess(
        this.aiGeneratedDescription,
        this.correctWord,
        this.currentCategory,
        this.currentDifficulty,
        this.forbiddenWords,
        undefined,
        true  // description_approved = true (AI description is always valid)
      )
      .subscribe({
        next: (response) => {
          if (reqId !== this.guessReqId) return;

          const elapsedMs = Date.now() - requestStartTime;
          const elapsedSeconds = Math.round(elapsedMs / 1000);
          if (elapsedSeconds > 0) {
            this.timerChanged.emit({ aiGuessTimeDiff: -elapsedSeconds });
          }

          const guessText = (response?.guess ?? "").trim();
          this.aiGuess = guessText;

          const backendCorrect = !!response?.is_correct;
          const localExact = guessText.toLowerCase() === (this.correctWord ?? "").trim().toLowerCase();
          this.isAiGuessCorrect = backendCorrect || localExact;
          this.aiGuessChecked = true;
          this.isThinking = false;

          if (this.isAiGuessCorrect) {
            // ── Percentage-based bonus for AI correct guess ──
            const bonus = this.calcBonus(elapsedMs);
            this.timerChanged.emit({ aiGuessTimeDiff: bonus });

            this.feedback = `Correct! The AI guessed it from the AI-generated description. +${bonus}s`;
            this.soundService.playCorrect();
            this.gameService.aiStats.correct++;
            this.endRoundAndAdvance("win");
          } else {
            this.localWrongGuesses++;
            this.gameService.aiStats.wrong++;
            this.timerChanged.emit({ aiGuessTimeDiff: -10 });
            this.feedback = `Wrong. The AI guessed: "${guessText}"`;
            this.soundService.playWrong();

            if (this.localWrongGuesses >= 3) {
              this.feedback = `The correct word was: ${this.correctWord}`;
              this.endRoundAndAdvance("loss");
            } else if (this.localWrongGuesses === 2) {
              this.isHintPhase = true;
              this.feedback = "AI: I'm not sure. Can you give me a hint?";
            }
          }
        },
        error: (err) => {
          if (reqId !== this.guessReqId) return;
          this.isThinking = false;
          this.feedback = "Failed to get AI guess. Please try again.";
        },
      });
  }

  // Start AI timer (emits -1 every second)
  private startAiTimer() {
    this.pauseTimer();
    this.timer = setInterval(() => {
      this.timerChanged.emit({ aiGuessTimeDiff: -1 });
    }, 1000);
  }

  // Stop AI timer
  private stopAiTimer() {
    this.pauseTimer();
  }

  makeAiGuess(input: string, durationMs?: number, isHint: boolean = false) {
    const reqId = ++this.guessReqId;

    if (this.localWrongGuesses === 1 && this.aiGuess) {
      input = input + " The word is not " + this.aiGuess;
    }

    this.refereeErrorMsg = "";
    this.refereeViolations = [];
    this.feedback = "";
    this.aiGuessChecked = false;
    this.isAiGuessCorrect = false;
    this.isThinking = true;

    // For hint path: description already approved, start timer immediately
    if (this.descriptionApproved) { this.startAiTimer(); }

    // Phase 1 (new description): validate first, then start timer + guess
    // Phase 2 (hint/re-guess):   skip validation, timer already running
    const validateCall = this.descriptionApproved
      ? this.gameService.makeGuess(
          input, this.correctWord, this.currentCategory, this.currentDifficulty,
          this.forbiddenWords, durationMs, true
        ).pipe(map(r => ({ type: 'guess' as const, response: r })))
      : this.gameService.validateDescription(
          input, this.correctWord, this.currentCategory, this.currentDifficulty,
          this.forbiddenWords, durationMs
        ).pipe(
          switchMap(() => {
            if (reqId !== this.guessReqId) return EMPTY;
            // Approved — start AI timer NOW, then call /guess
            this.descriptionApproved = true;
            this.localUncompliantCount = 0;
            this.startAiTimer();
            return this.gameService.makeGuess(
              input, this.correctWord, this.currentCategory, this.currentDifficulty,
              this.forbiddenWords, durationMs, true
            ).pipe(map(r => ({ type: 'guess' as const, response: r })));
          })
        );

    const guessStartTime = Date.now();

    validateCall.subscribe({
        next: (wrapped) => {
          if (reqId !== this.guessReqId) return;
          this.stopAiTimer();

          // Apply -2 hint penalty only now that the hint was accepted as valid
          if (isHint) {
            this.timerChanged.emit({ aiGuessTimeDiff: -2 });
          }

          // unwrap: hint path returns GuessResponse directly, description path wraps it
          const response = (wrapped as any)?.response ?? wrapped as any;

          const guessText = (response?.guess ?? "").trim();
          this.aiGuess = guessText;

          const backendCorrect = !!response?.is_correct;
          const localExact = guessText.toLowerCase() === (this.correctWord ?? "").trim().toLowerCase();
          this.isAiGuessCorrect = backendCorrect || localExact;
          this.aiGuessChecked = true;

          const elapsedMs = Date.now() - guessStartTime;

          if (this.isAiGuessCorrect) {
            // ── Percentage-based bonus for AI correct guess ──
            const bonus = this.calcBonus(elapsedMs);
            this.timerChanged.emit({ aiGuessTimeDiff: bonus });

            this.feedback = `Correct! The AI guessed it! +${bonus}s`;
            this.soundService.playCorrect();
            this.gameService.aiStats.correct++;
            this.isHintPhase = false;
            this.isThinking = false;

            this.commentaryService.generate(
              "The AI guessed the word correctly!",
              { word: this.correctWord, category: this.currentCategory, attempt: this.localWrongGuesses + 1 },
              (msg) => this.showFeedbackCommentary(msg, 'positive')
            );

            this.endRoundAndAdvance("win");
          } else {
            this.feedback = "Wrong.";
            this.soundService.playWrong();
            this.gameService.aiStats.wrong++;

            this.timerChanged.emit({ aiGuessTimeDiff: -10 });

            this.localWrongGuesses++;
            this.isThinking = false;

            if (this.localWrongGuesses === 2) {
              this.commentaryService.generate(
                "The AI guessed wrong twice and is now asking for a hint.",
                { guess: guessText, category: this.currentCategory, attempt: 2 },
                (msg) => this.showFeedbackCommentary(msg, 'negative')
              );

              setTimeout(() => {
                if (reqId !== this.guessReqId) return;
                this.isHintPhase = true;
                this.feedback = "AI: I'm not sure. Can you give me a hint?";
              }, 3000);
            } else if (this.localWrongGuesses >= 3) {
              this.commentaryService.generate(
                "The AI failed to guess the word after 3 attempts. The round is lost.",
                { word: this.correctWord, category: this.currentCategory },
                (msg) => this.showFeedbackCommentary(msg, 'negative')
              );

              this.feedback = `The correct word was: ${this.correctWord}`;
              this.isHintPhase = false;
              this.endRoundAndAdvance("loss");
            } else {
              this.commentaryService.generate(
                "The AI guessed wrong on its first attempt.",
                { guess: guessText, category: this.currentCategory, attempt: 1 },
                (msg) => this.showFeedbackCommentary(msg, 'warning')
              );
            }
          }
        },

        error: (err) => {
          if (reqId !== this.guessReqId) return;
          this.stopAiTimer();

          this.isThinking = false;
          this.aiGuessChecked = false;
          this.isAiGuessCorrect = false;

          const parsed = this.parseBackendError(err);

          if (err?.status === 400 && parsed?.violations?.length) {
            this.refereeErrorMsg =
              parsed.message ||
              "Your description violates the rules. Please revise and try again.";

            this.refereeViolations = parsed.violations;
            this.localUncompliantCount++;
            const remaining = this.MAX_UNCOMPLIANT - this.localUncompliantCount;

            if (this.localUncompliantCount >= this.MAX_UNCOMPLIANT) {
              this.localUncompliantCount = 0;
              this.refereeErrorMsg = "";
              this.refereeViolations = [];
              this.triggerAiDescriptionOverride();
            } else {
              this.refereeErrorMsg += ` (${remaining} left before AI takes over)`;

              this.commentaryService.generate(
                "The referee rejected the player's description for violating the rules.",
                {},
                (msg) => this.showCommentary(msg, 'warning')
              );
            }

            return;
          }

          this.feedback = "Failed to get AI guess. Please try again.";
        },
      });
  }

  // Trigger AI description override after 3 violations
  private triggerAiDescriptionOverride() {
    this.isGeneratingAiDescription = true;
    this.aiDescriptionOverride = false;
    this.feedback = "";
    this.refereeErrorMsg = "";

    const roundId = this.gameService.getCurrentRoundId();
    if (!roundId) {
      this.feedback = "Could not generate AI description — no round ID.";
      this.isGeneratingAiDescription = false;
      return;
    }

    this.commentaryService.generate(
      "The player submitted 3 invalid descriptions. The AI is now taking over and generating the description itself.",
      { round: this.roundNumber },
      (msg) => this.showCommentary(msg, 'warning')
    );

    this.gameService.generateDescription(roundId, this.forbiddenWords).subscribe({
      next: (res) => {
        this.aiGeneratedDescription = res.description || "";
        this.userDescription = this.aiGeneratedDescription;
        this.aiDescriptionOverride = true;
        this.isGeneratingAiDescription = false;

        setTimeout(() => {
          this.submitAiGeneratedDescription();
        }, 2000);
      },
      error: (err) => {
        console.error("Failed to generate AI description", err);
        this.isGeneratingAiDescription = false;
        this.feedback = "Failed to generate AI description. Please try again.";
      },
    });
  }

  private endRoundAndAdvance(outcome: "win" | "loss" | "timeout" | "quit") {
    if (this.roundEnded) return;
    this.roundEnded = true;
    this.showingResult = true;

    this.pauseTimer();

    this.gameService.endRound(outcome).subscribe({
      next: (response) => {
        if (response?.next_difficulty) {
          this.difficultyChanged.emit(response.next_difficulty);
        }
      },
      error: (e) => console.warn("end-round failed:", e),
    });

    setTimeout(() => {
      this.showingResult = false;
      this.roundCompleted.emit();
    }, 4500);
  }

  private parseBackendError(err: any): { message?: string; violations?: string[] } {
    let body: any = err?.error;
    if (typeof body === "string") {
      try { body = JSON.parse(body); } catch { return { message: body }; }
    }
    const message = body?.error || body?.message || err?.message;
    const violationsRaw = body?.violations;
    let violations: string[] = [];
    if (Array.isArray(violationsRaw)) {
      violations = violationsRaw.map((v: any) => v?.message ?? v?.code ?? String(v));
    }
    return { message, violations };
  }

  resetStateForNextWord() {
    this.userDescription = "";
    this.userHint = "";
    this.aiGuess = "";
    this.feedback = "";
    this.refereeErrorMsg = "";
    this.refereeViolations = [];
    this.isAiGuessCorrect = false;
    this.aiGuessChecked = false;
    this.localWrongGuesses = 0;
    this.hintUsed = 0;
    this.isHintPhase = false;
    this.forbiddenWords = [];
    this.isForbiddenLoading = false;
    this.localUncompliantCount = 0;
    this.descriptionStartTime = 0;
    this.descriptionApproved = false;
    this.roundEnded = false;
    this.showingResult = false;
    this.commentaryMessage = "";
    this.aiDescriptionOverride = false;
    this.aiGeneratedDescription = "";
    this.isGeneratingAiDescription = false;
  }

  handleSkip() {
    this.timerChanged.emit({ userGuessTimeDiff: -2 });
    this.gameService.userStats.skipped++;

    this.loggingService.logEvent("userSkippedWord", {
      roundNumber: this.roundNumber,
      difficulty: this.currentDifficulty,
      phase: "ai-guess",
      reason: "user_clicked_change_word",
      descriptionLength: this.userDescription.trim().length,
    });

    this.commentaryService.generate(
      "The player decided to skip this word and get a new one.",
      { round: this.roundNumber },
      (msg) => this.showCommentary(msg, 'neutral')
    );

    this.fetchWordForUserToDescribe();
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
    this.pauseTimer();
    if (!this.roundEnded) {
      const outcome: "win" | "loss" | "timeout" | "quit" =
        this.isAiGuessCorrect ? "win"
        : this.gameOver ? "timeout"
        : this.localWrongGuesses >= 3 ? "loss"
        : "quit";
      this.endRoundAndAdvance(outcome);
    } else {
      this.roundCompleted.emit();
    }
  }

  logStartRound() {
    this.loggingService.logEvent("aiGuessRoundStarted", {
      roundNumber: this.roundNumber,
      difficulty: this.currentDifficulty,
      phase: "ai-guess",
    });
  }
}
