import { bootstrapApplication } from "@angular/platform-browser";
import { provideRouter, Routes, RouterOutlet } from "@angular/router";
import { provideHttpClient } from "@angular/common/http";
import { Component } from "@angular/core";
import { GameModeSelectionComponent } from "./app/components/game-mode-selection/game-mode-selection.component";
import { WinnerComponent } from "./app/components/winner/winner.component";
import { GameComponent } from "./app/components/game/game.component";
import { LoginComponent } from "./app/components/login/login.component";
import { GameOverComponent } from "./app/components/game-over/game-over.component";

const routes: Routes = [
  { path: "", component: LoginComponent },
  { path: "mode-selection", component: GameModeSelectionComponent },
  //{ path: 'user-guesses', component: UserGuessesComponent },
  //{ path: 'ai-guesses', component: AiGuessesComponent },
  { path: "winner", component: WinnerComponent },
  { path: "game", component: GameComponent },
  { path: "game-over", component: GameOverComponent },
];

@Component({
  selector: "app-root",
  template: `<router-outlet></router-outlet>`,
  standalone: true,
  imports: [RouterOutlet],
})
export class App {}

bootstrapApplication(App, {
  providers: [provideRouter(routes), provideHttpClient()],
});
