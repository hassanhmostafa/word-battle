// src/app/services/sound.service.ts
import { Injectable } from "@angular/core";

@Injectable({
  providedIn: "root",
})
export class SoundService {
  private readonly audioCache = new Map<string, HTMLAudioElement>();

  constructor() {
    ["correct", "wrong", "win", "game-over"].forEach((name) => {
      const audio = new Audio(`assets/sounds/${name}.wav`);
      audio.preload = "auto";
      this.audioCache.set(name, audio);
    });
  }

  play(name: string) {
    const cachedAudio = this.audioCache.get(name);
    const audio = cachedAudio ? cachedAudio.cloneNode(true) as HTMLAudioElement : new Audio(`assets/sounds/${name}.wav`);
    audio.preload = "auto";
    audio.currentTime = 0;
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
