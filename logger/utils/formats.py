#!/usr/bin/env python3

"""Set of hierarchical utility classes used to check for input/output
compatibility between Readers, Writers and Transforms.

The idea is that each class defined here (or elsewhere) represents a
particular data exchange format, including everything from raw binary
(Bytes) to JSON encodings of RVDAS Records (JSON_Record). Processes
that accept inputs higher in the inheritance tree can also accept
inputs that inherit from them. So something that accepts Text can also
accept NMEA or XML, but not vice versa.

The only methods defined here are class methods belonging to the base
class (Bytes):

  A.can_accept(B) - true iff format A can accept format B, e.g.
     assertTrue(JSON.can_accept(JSON_Record))

  A.common(B) - the lowest common format A and B share, e.g.
     XML.common(JSON_Record) == Text

Reader objects are intended to be instantiated such that their
output_format() method returns a format class, and Writers such that
their input_format() method also returns one. It is the responsibility
of whatever program look encloses them to ensure compatibility by
checking that

  writer.input_format().can_accept(reader.output_format())

Transforms have both an input_format() and output_format(), with the
unsolved complication that, for some transforms, the output format
depends on the input format.

Currently-defined format hierarchy is:

    Bytes
      Text
        NMEA
        JSON - generic JSON string
          JSON_Record - JSON string representing a DAS Record
        XML
          XML_OSU
      Python - e.g. a dict or list
        Python_Record - a Python DAS Record

There is also a special case 'Unknown' format that can't accept
anything, and has no common elements with any other format.

"""

########################################
# Test whether the passed object is actually a valid format, as
# defined in this file.


def is_format(format):
    # Is format even a class?
    if not isinstance(format, type(Bytes)):
        return False

    # Is it a class that inherits from one of the format classes defined here?
    if format == Unknown or Bytes.can_accept(format):
        return True

    return False

########################################
# 'Unknown' is a special case format - it can't accept anything, and
# has no other common formats


class Unknown:
    @classmethod
    def can_accept(self, other_format):
        return False

    @classmethod
    def common(self, other_format):
        return None

########################################
# 'Bytes' is the highest, most general format in the hierarchy. All
# more-specific formats inherit from it.


class Bytes:
    @classmethod
    def can_accept(self, other_format):
        return self in other_format.mro()

    # Most specific common format
    @classmethod
    def common(self, other_format):
        # We have nothing in common with Unknown
        if not other_format or other_format == Unknown:
            return None

        # Chase up module resolution order of superclasses for a match
        other_hierarchy = other_format.mro()
        for c in self.mro():
            if c in other_hierarchy:
                return c
        # Shouldn't actually get here, but...
        return None


class Text(Bytes):
    pass


class NMEA(Text):
    pass


class JSON(Text):
    pass


class JSON_Record(JSON):
    pass


class Python(Bytes):
    pass


class Python_Record(Python):
    pass


class XML(Text):
    pass


class XML_OSU(XML):
    pass
