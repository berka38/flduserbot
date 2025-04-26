import os
import subprocess
from app import create_app, db
from app.models import User, TelegramAccount, CustomCommand, PythonCommand, Notification, CommandCategory, CommandRating, AnimalSpecies, UserAnimal
import click

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'TelegramAccount': TelegramAccount, 
            'CustomCommand': CustomCommand, 'PythonCommand': PythonCommand,
            'Notification': Notification, 'CommandCategory': CommandCategory,
            'CommandRating': CommandRating,
            'AnimalSpecies': AnimalSpecies,
            'UserAnimal': UserAnimal}

@app.cli.command('seed_animals')
def seed_animals():
    """Seeds the database with initial animal species data."""
    animals_data = [
        {'name': 'Dog', 'emoji': '🐶', 'rarity': 'Common', 'base_value': 10},
        {'name': 'Cat', 'emoji': '🐱', 'rarity': 'Common', 'base_value': 10},
        {'name': 'Rabbit', 'emoji': '🐰', 'rarity': 'Common', 'base_value': 15},
        {'name': 'Fox', 'emoji': '🦊', 'rarity': 'Uncommon', 'base_value': 30},
        {'name': 'Deer', 'emoji': '🦌', 'rarity': 'Uncommon', 'base_value': 40},
        {'name': 'Bear', 'emoji': '🐻', 'rarity': 'Rare', 'base_value': 75},
        {'name': 'Wolf', 'emoji': '🐺', 'rarity': 'Rare', 'base_value': 80},
        {'name': 'Eagle', 'emoji': '🦅', 'rarity': 'Epic', 'base_value': 150},
        {'name': 'Lion', 'emoji': '🦁', 'rarity': 'Epic', 'base_value': 160},
        {'name': 'Dragon', 'emoji': '🐉', 'rarity': 'Mythical', 'base_value': 500},
        {'name': 'Unicorn', 'emoji': '🦄', 'rarity': 'Mythical', 'base_value': 550},
    ]
    
    added_count = 0
    with app.app_context():
        for data in animals_data:
            exists = AnimalSpecies.query.filter_by(name=data['name']).first()
            if not exists:
                animal = AnimalSpecies(name=data['name'], emoji=data['emoji'], rarity=data['rarity'], base_value=data['base_value'])
                db.session.add(animal)
                added_count += 1
        
        if added_count > 0:
            db.session.commit()
            click.echo(f'Added {added_count} new animal species to the database.')
        else:
            click.echo('All animal species already exist in the database.')

if __name__ == "__main__":
    if not os.path.exists('instance'):
        os.makedirs('instance')
        print("--- Created instance folder")
        
    # Use debug=False in production
    # Consider using a production server like Gunicorn or Waitress
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
    app.run(debug=True) 
