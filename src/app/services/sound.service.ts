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
      audio.load();
      this.audioCache.set(name, audio);
    });
  }

  private getOrCreateAudio(name: string): HTMLAudioElement {
    let audio = this.audioCache.get(name);
    if (!audio) {
      audio = new Audio(`assets/sounds/${name}.wav`);
      audio.preload = "auto";
      audio.load();
      this.audioCache.set(name, audio);
    }
    return audio;
  }

  play(name: string) {
    const audio = this.getOrCreateAudio(name);
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch {}

    const playPromise = audio.play();
    if (playPromise) {
      playPromise.catch((error) => {
        console.error(`Error playing sound '${name}':`, error);
      });
    }
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
