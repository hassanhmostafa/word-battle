import { Component, OnInit } from "@angular/core";
import { CommonModule } from "@angular/common";
import { Router } from "@angular/router";
import { FormsModule } from "@angular/forms";
import { INITIAL_TIME } from "../../services/game.service";

@Component({
  selector: "app-login",
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: "./login.component.html",
  styleUrls: ["./login.component.scss"],
})
export class LoginComponent implements OnInit {
  username = "";
  existingUsername = "";
  isReturningUser = false;
  initialTime = INITIAL_TIME;

  constructor(private router: Router) {}

  ngOnInit() {
    // Check if user already has a username (returning user)
    this.existingUsername = localStorage.getItem("username") || "";
    if (this.existingUsername) {
      this.username = this.existingUsername;
      this.isReturningUser = true;
    }
  }

  startGame() {
    if (this.username.trim()) {
      // Store username in localStorage
      localStorage.setItem("username", this.username.trim());
      
      // Navigate to game
      this.router.navigate(["/mode-selection"]);
    }
  }
}