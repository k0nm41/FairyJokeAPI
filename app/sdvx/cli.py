import click

from . import bp

@bp.cli.command()
@click.argument('path')
def load_data(path):
    from .consumer import import_from_game_data

    import_from_game_data(path)
