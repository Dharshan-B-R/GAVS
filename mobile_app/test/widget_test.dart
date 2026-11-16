
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/main.dart';

void main() {
  group('KiranaAI Login Screen', () {
    Future<void> openLoginScreen(
      WidgetTester tester, {
      String? error,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          home: LoginScreen(
            onLogin: () {},
            initialError: error,
          ),
        ),
      );
    }

    testWidgets('displays KiranaAI login screen', (tester) async {
      await openLoginScreen(tester);

      expect(find.text('KiranaAI'), findsOneWidget);
      expect(find.text('Sign in to manage your shop'), findsOneWidget);
      expect(find.text('Email'), findsOneWidget);
      expect(find.text('Password'), findsOneWidget);
      expect(find.text('Sign in'), findsOneWidget);
      expect(find.text('Create an Owner or Supplier account'), findsOneWidget);
      expect(find.text('Join a shop with an employee invitation'), findsOneWidget);
    });

    testWidgets('validates empty email and password', (tester) async {
      await openLoginScreen(tester);

      await tester.tap(find.text('Sign in'));
      await tester.pump();

      expect(find.text('Enter a valid email'), findsOneWidget);
      expect(find.text('Enter your password'), findsOneWidget);
    });

    testWidgets('rejects invalid email format', (tester) async {
      await openLoginScreen(tester);

      await tester.enterText(find.byType(TextFormField).at(0), 'invalid-email');
      await tester.enterText(find.byType(TextFormField).at(1), 'password123');

      await tester.tap(find.text('Sign in'));
      await tester.pump();

      expect(find.text('Enter a valid email'), findsOneWidget);
    });

    testWidgets('toggles password visibility', (tester) async {
      await openLoginScreen(tester);

      expect(find.byIcon(Icons.visibility), findsOneWidget);

      await tester.tap(find.byIcon(Icons.visibility));
      await tester.pump();

      expect(find.byIcon(Icons.visibility_off), findsOneWidget);
    });

    testWidgets('displays authentication error', (tester) async {
      await openLoginScreen(
        tester,
        error: 'Invalid email or password',
      );

      expect(find.text('Invalid email or password'), findsOneWidget);
    });
  });
}
