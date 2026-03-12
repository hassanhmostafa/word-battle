import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';


@Component({
  selector: 'app-game-mode-selection',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './game-mode-selection.component.html',
  styleUrls: ['./game-mode-selection.component.css']
})
export class GameModeSelectionComponent {
  constructor(private router: Router) {}

  startGame(): void {
    // ✅ CRITICAL: Clear ALL old game data
    localStorage.removeItem('current_round_id');
    localStorage.removeItem('current_game_id');
    
    // ✅ CRITICAL: Set new_game flag so backend creates a fresh game
    // This flag is read by game.service.ts on the FIRST API call
    // and sent to the backend as new_game=true
    // The backend will close any old unfinished games and create a new one
    localStorage.setItem('new_game', 'true');
    
    console.log('🎮 Starting new game - cleared old data, set new_game flag');
    
    // Navigate to the game
    this.router.navigate(['/game']);
  }
}
