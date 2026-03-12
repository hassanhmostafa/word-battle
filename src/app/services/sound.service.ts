// src/app/services/sound.service.ts
import { Injectable } from "@angular/core";

@Injectable({
  providedIn: "root",
})
export class SoundService {
  play(name: string) {
    const audio = new Audio();
    audio.src = `assets/sounds/${name}.wav`;
    audio.load();
    audio.play().catch((error) => {
      console.error(`Error playing sound '${name}':`, error);
    });
  }

  playCorrect() {
    this.play("correct");
  }

  playWrong() {
    this.play("wrong");
  }

  playWin() {
    this.play("win");
  }

  playGameOver() {
    this.play("game-over");
  }
}
